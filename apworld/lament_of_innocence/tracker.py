"""The map tracker: the castle's map, Leon's live position and the slot's locations, shown in the
client window's Map tab (map_view.py, 2D) and on a local web page (/map in the client opens it, 3D).

The client's own game loop calls MapTracker.tick() with its PINE connection, so the tracker needs
no second connection (PCSX2's PINE takes one client at a time). Shapes are captured from the game
the first time Leon is in an area (mapshapes.py) and kept in the cache folder, so a map seen once
shows even while PCSX2 is off. The page (data/tracker/index.html) polls /api/state.

No Archipelago imports: tools/test_map_tracker.py runs it against an in-memory fake.
"""
from __future__ import annotations

import json
import math
import os
import pkgutil
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import mapshapes as ms

FORMAT = 1                 # bump when the cache layout changes (older caches are rebuilt)
DEFAULT_PORT = 38410
VISITED_INTERVAL = 2.0     # seconds between reads of the visited table (~5 KB)


def _page() -> bytes:
    raw = pkgutil.get_data(__package__ or __name__.rpartition(".")[0], "data/tracker/index.html")
    if raw is None:
        raise FileNotFoundError("data/tracker/index.html")
    return raw


class Area:
    """One decoded map file."""

    def __init__(self, file_id: int, data: bytes, base: int):
        self.id, self.base = file_id, base
        self.tris, self.pieces, self.local = ms.build_area(data, base)
        self.stages = sorted({p["stage"] for p in self.pieces})

    def info(self) -> dict:
        return {"id": self.id, "stages": self.stages, "local": self.local,
                "triangles": len(self.tris) // 24, "pieces": self.pieces}

    def lowest_piece(self, stage: int, room: int) -> Optional[dict]:
        mine = [p for p in self.pieces if p["stage"] == stage and p["room"] == room]
        return min(mine, key=lambda p: p["floor"]) if mine else None


class MapTracker:
    def __init__(self, cache: Path):
        self.cache = Path(cache)
        self.lock = threading.Lock()
        self.areas: Dict[int, Area] = {}
        self.doors: Dict[str, List[dict]] = {}     # "stage:room" -> doors in map space
        self.version = 0                            # bumped when areas or doors change
        self.state: dict = {"connected": False}
        self.ap: dict = {}
        self.server: Optional[ThreadingHTTPServer] = None
        self.url = ""
        self.enabled = False                        # the client window's Map tab is reading it
        self._reset_session()
        self._load_cache()

    # ---- cache ----
    def _raw(self, name: str) -> Path:
        return self.cache / name

    def _load_cache(self) -> None:
        try:
            meta = json.loads(self._raw("maps.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if meta.get("format") != FORMAT:
            return
        for entry in meta.get("files", []):
            try:
                data = self._raw(f"mapfile_{entry['id']}.bin").read_bytes()
                self.areas[entry["id"]] = Area(entry["id"], data, entry["base"])
            except (OSError, ValueError, KeyError, struct.error, IndexError):
                continue
        self.doors = meta.get("doors", {})
        self.version += 1

    def _save_cache(self) -> None:
        self.cache.mkdir(parents=True, exist_ok=True)
        meta = {"format": FORMAT, "files": [{"id": a.id, "base": a.base} for a in self.areas.values()],
                "doors": self.doors}
        tmp = self._raw("maps.json.tmp")
        tmp.write_text(json.dumps(meta), encoding="utf-8")
        os.replace(tmp, self._raw("maps.json"))

    # ---- game side (called from the client's game loop, in a worker thread) ----
    def _reset_session(self) -> None:
        self.first_keys: List[int] = []
        self.floor_heights: List[float] = []
        self.visited: List[int] = []
        self.visited_at = 0.0
        self.seen_file: Optional[Tuple[int, int]] = None

    def disconnected(self) -> None:
        """The client lost PCSX2: the next tick re-reads the per-boot tables."""
        self._reset_session()
        with self.lock:
            self.state = {"connected": False}

    def tick(self, mem: ms.Memory) -> None:
        if not self.first_keys:
            self.first_keys, _counts = ms.read_room_table(mem)
            if self.first_keys:
                self.floor_heights = ms.read_floor_heights(mem, len(self.first_keys))
        leon = ms.read_leon(mem)
        changed = self._capture_map(mem, leon)
        area = self.areas.get(leon["map_file_id"])
        piece = None
        if area:
            stage = leon["stage"]
            height = self.floor_heights[stage] if stage < len(self.floor_heights) else 0.0
            piece = ms.current_piece(area.pieces, stage, leon["room"], leon["y"], height)
            changed |= self._capture_doors(mem, leon, piece)
        now = time.monotonic()
        if now - self.visited_at > VISITED_INTERVAL:
            self.visited_at = now
            self.visited = ms.read_visited(mem) or self.visited
        player = None
        if piece:
            mx, mz = ms.world_to_map(piece, leon["x"], leon["z"])
            # Leon faces world (sin yaw, cos yaw): carry that through the same transform
            fx, fz = ms.world_to_map(piece, leon["x"] + 100 * math.sin(leon["yaw"]),
                                     leon["z"] + 100 * math.cos(leon["yaw"]))
            length = math.hypot(fx - mx, fz - mz) or 1.0
            player = {"x": mx, "z": mz, "floor": piece["floor"],
                      "dir": [(fx - mx) / length, (fz - mz) / length]}
        if changed:
            self._save_cache()
        with self.lock:
            if changed:
                self.version += 1
            self.state = {"connected": True, "area": leon["map_file_id"], "stage": leon["stage"],
                          "room": leon["room"], "player": player, "visited": self.visited,
                          "first_keys": self.first_keys}

    def _capture_map(self, mem: ms.Memory, leon: dict) -> bool:
        file_id, ptr = leon["map_file_id"], leon["map_file"]
        if file_id <= 0 or not ms.in_ram(ptr) or file_id in self.areas:
            self.seen_file = None
            return False
        # the same file twice in a row: a file still loading can sit at the old one's address
        if self.seen_file != (file_id, ptr):
            self.seen_file = (file_id, ptr)
            return False
        try:
            data = ms.copy_map_file(mem, ptr)
            area = Area(file_id, data, ptr)
        except (ms.MapShapeError, struct.error, IndexError):
            return False
        if leon["stage"] not in area.stages:   # the previous area's file, not this one yet
            return False
        self.cache.mkdir(parents=True, exist_ok=True)
        self._raw(f"mapfile_{file_id}.bin").write_bytes(data)
        with self.lock:
            self.areas[file_id] = area
        return True

    def _capture_doors(self, mem: ms.Memory, leon: dict, piece: Optional[dict]) -> bool:
        key = f"{leon['stage']}:{leon['room']}"
        if key in self.doors or not piece or not ms.in_ram(leon["roomdata"]):
            return False
        doors = []
        for d in ms.read_doors(mem, leon["roomdata"]):
            mx, mz = ms.world_to_map(piece, d["x"], d["z"])
            doors.append({"area": leon["map_file_id"], "floor": piece["floor"], "x": mx, "z": mz,
                          "dest": d["dest"]})
        with self.lock:
            self.doors[key] = doors
        return True

    # ---- Archipelago side (called from the client) ----
    def set_ap(self, ap: dict) -> None:
        """What the page shows of the slot: {"slot": name, "rooms": {room_key: [[name, checked],
        ...]}, "torches": [{"name", "stage", "room", "x", "z" (world), "checked"}]}."""
        with self.lock:
            self.ap = ap

    def _torches(self) -> List[dict]:
        out = []
        for t in self.ap.get("torches", []):
            for area in self.areas.values():
                p = area.lowest_piece(t["stage"], t["room"])
                if p:
                    mx, mz = ms.world_to_map(p, t["x"], t["z"])
                    out.append({"area": area.id, "floor": p["floor"], "x": mx, "z": mz,
                                "name": t["name"], "checked": t["checked"]})
                    break
        return out

    # ---- web ----
    def snapshot(self) -> dict:
        with self.lock:
            state = dict(self.state)
            state["version"] = self.version
            state["slot"] = self.ap.get("slot")
            state["rooms"] = self.ap.get("rooms", {})
            state["torches"] = self._torches()
            state["doors"] = [d for doors in self.doors.values() for d in doors]
            return state

    def maps(self) -> dict:
        with self.lock:
            return {"version": self.version, "areas": [a.info() for a in self.areas.values()]}

    def area_bin(self, file_id: int) -> Optional[bytes]:
        with self.lock:
            area = self.areas.get(file_id)
            return area.tris if area else None

    def start(self, port: int = DEFAULT_PORT) -> str:
        """Start the web server (once); returns its URL."""
        if self.server:
            return self.url
        tracker, page = self, _page()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def _send(self, body: bytes, kind: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                if path in ("/", "/index.html"):
                    return self._send(page, "text/html; charset=utf-8")
                if path == "/api/state":
                    return self._send(json.dumps(tracker.snapshot()).encode(), "application/json")
                if path == "/api/maps":
                    return self._send(json.dumps(tracker.maps()).encode(), "application/json")
                if path.startswith("/api/area/"):
                    try:
                        body = tracker.area_bin(int(path.rsplit("/", 1)[1]))
                    except ValueError:
                        body = None
                    if body is not None:
                        return self._send(body, "application/octet-stream")
                self.send_error(404)

        # then any free port: Hyper-V / WSL can reserve whole ranges around the default
        for p in [*range(port, port + 20), 0]:
            try:
                self.server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
                break
            except OSError:
                continue
        if not self.server:
            raise OSError("no free port for the map tracker")
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, name="map tracker", daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"
        return self.url

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
