"""The map tracker's shapes and Leon's place on them, read from the player's own game over PINE
(nothing from the game ships with the .apworld).

Shapes: the pause map's model (src/game.h "area map"). Each area has one map file; every room is a
piece (stage, room, floor, position, yaw, scale) whose meshes are the room's floor shape (kind 1
parts) and wall band (kind 0 parts). The mesh decoder is a port of src/minimap.c. The pause map
is flat: floors are stacked by the piece's floor number.

Leon: the pause map marker's formula (0x6C3EB8), piece.pos + piece.scale * RotY(piece.yaw) *
0.1 * (x, 0, z), on the piece Map_GetCurrentPiece (0x6C1048 -> 0x6C0E90) picks: of the room's
pieces, the one on floor lowest + int(|Leon y| / floor_height[stage]) (clamped to the room's
pieces; floor heights @ 0x798328, float per stage).

No Archipelago imports: tools/test_map_tracker.py runs it against an in-memory fake.
"""
from __future__ import annotations

import math
import struct
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

# ---- game addresses (src/game.h) ----
CUR_STAGE = 0x00738E94          # u16 stage, u16 room
ROOM_TABLE_PTR = 0x00738E90
ROOM_STATE_PTR = 0x00797D40     # u32[3] per room key, bit 0 = visited (the pause map's flag)
ROOM_STATE_COUNT = 0x00797D44
FLOOR_HEIGHTS = 0x00798328      # float per stage: world units per map floor
PLAYER_POS = 0x00B63430         # float x, y, z (world Y points down)
PLAYER_MODEL = 0x00B632C0       # model pointer; rotation (x, y, z) at +0xD0
MODEL_YAW = 0xD4
ROOMDATA = 0x00B5F4E0
MAP_FILE_ID = 0x00B90970        # int disc file ID, then the file pointer
MAP_FILE = 0x00B90974

PIECE_SIZE = 0x60
PIECE_ROOM, PIECE_FLOOR, PIECE_FLAGS, PIECE_COUNTS = 0x01, 0x02, 0x08, 0x10
PIECE_WALL_PARTS, PIECE_FLOOR_PARTS = 0x1A, 0x1E   # u8[4] each: kind 0 (wall band), kind 1 (floor)
PIECE_POS, PIECE_SCALE = 0x40, 0x50
PIECE_FLAG_SAVE = 0x0002
MODEL_NODE_OFS, MODEL_NODE_COUNT, MODEL_MESH_COUNT, MODEL_MESH_OFS = 0x08, 0x0C, 0x20, 0x24
MESH_PART = 0x43
MESH_MIN, MESH_MAX = 0x50, 0x10000
VIF_UNPACK_V3_32, VIF_UNPACK_V4_16 = 0x68, 0x6D
ROOMDATA_OBJLISTS = 0x04
OBJ_REC = 0x80
DOOR_DEST = 0x50                # s16 stage, room, object list, entrance

RAM_LO, RAM_HI = 0x00100000, 0x02000000


class Memory(Protocol):
    def read(self, addr: int, length: int) -> bytes: ...


class MapShapeError(ValueError):
    """The map file isn't (fully) there or isn't laid out as expected."""


def in_ram(addr: int) -> bool:
    return RAM_LO <= addr < RAM_HI


def _u32(b: bytes, o: int = 0) -> int:
    return struct.unpack_from("<I", b, o)[0]


def _i32(b: bytes, o: int = 0) -> int:
    return struct.unpack_from("<i", b, o)[0]


def _word(mem: Memory, addr: int) -> int:
    return _u32(mem.read(addr, 4))


# ---- copying a map file out of the game ----

def map_file_extent(mem: Memory, base: int) -> int:
    """Byte length of the pause map file at `base`: the pieces, then the model and its meshes."""
    head = mem.read(base, 8)
    if _u32(head) != 1:
        raise MapShapeError("map file not relocated yet (still loading)")
    count = _i32(head, 4)
    if not 0 < count < 1024:
        raise MapShapeError(f"bad piece count {count}")
    last_piece = _word(mem, base + 0x30 + 4 * (count - 1))
    if not in_ram(last_piece):
        raise MapShapeError("bad piece pointer")
    model = _find_model(mem.read((last_piece + PIECE_SIZE + 15) & ~15, 0x80),
                        (last_piece + PIECE_SIZE + 15) & ~15)
    if model is None:
        raise MapShapeError("no model after the pieces")
    head = mem.read(model, 0x30)
    end = model + 0x30
    node_ofs, node_count = _i32(head, MODEL_NODE_OFS), _i32(head, MODEL_NODE_COUNT)
    if 0 < node_count < 1024:
        end = max(end, model + node_ofs + 64 * node_count)
    mesh_count, mesh = _i32(head, MODEL_MESH_COUNT), model + _i32(head, MODEL_MESH_OFS)
    for _ in range(max(0, min(mesh_count, 4096))):
        size = _word(mem, mesh)
        if not MESH_MIN <= size <= MESH_MAX:
            break
        mesh += size
    return max(end, mesh) - base


def _find_model(window: bytes, at: int) -> Optional[int]:
    for i in range(0, min(len(window), 0x80), 16):
        if _u32(window, i) & 0xFFFF0000 == 0xFFFF0000:
            return at + i
    return None


def copy_map_file(mem: Memory, base: int) -> bytes:
    return mem.read(base, map_file_extent(mem, base))


# ---- decoding a map file ----

class MapFile:
    """A copied map file. Its pointers are absolute EE addresses; `base` is where it was."""

    def __init__(self, data: bytes, base: int):
        self.d, self.base = data, base

    def _at(self, addr: int) -> int:
        o = addr - self.base
        if not 0 <= o < len(self.d):
            raise MapShapeError(f"pointer {addr:#x} outside the map file")
        return o

    def piece_offsets(self) -> List[int]:
        count = _i32(self.d, 4)
        return [self._at(_u32(self.d, 0x30 + 4 * i)) for i in range(count)]

    def pieces(self) -> List[dict]:
        out = []
        for i, o in enumerate(self.piece_offsets()):
            p = self.d[o:o + PIECE_SIZE]
            counts = struct.unpack_from("<5H", p, PIECE_COUNTS)
            out.append({
                "index": i, "stage": p[0], "room": p[PIECE_ROOM],
                "floor": struct.unpack_from("b", p, PIECE_FLOOR)[0],
                "flags": struct.unpack_from("<H", p, PIECE_FLAGS)[0],
                "pos": list(struct.unpack_from("<3f", p, PIECE_POS)),
                "yaw": struct.unpack_from("<f", p, PIECE_POS + 12)[0],
                "scale": list(struct.unpack_from("<3f", p, PIECE_SCALE)),
                "wall_parts": list(p[PIECE_WALL_PARTS:PIECE_WALL_PARTS + min(counts[0], 4)]),
                "floor_parts": list(p[PIECE_FLOOR_PARTS:PIECE_FLOOR_PARTS + min(counts[1], 4)]),
            })
        return out

    def model(self) -> int:
        offsets = self.piece_offsets()
        if not offsets:
            raise MapShapeError("no pieces")
        o = (offsets[-1] + PIECE_SIZE + 15) & ~15
        found = _find_model(self.d[o:o + 0x80], o)
        if found is None:
            raise MapShapeError("no model after the pieces")
        return found

    def parts_local(self, model: int) -> bool:
        """True when the part matrices place the parts: the meshes are then in each room's own
        frame (Anti-Soul Mystery Lab). Only the x translation counts (minimap.c)."""
        count = _i32(self.d, model + MODEL_NODE_COUNT)
        ofs = model + _i32(self.d, model + MODEL_NODE_OFS)
        if not 0 < count < 1024 or ofs + 64 * count > len(self.d):
            return False
        return any(abs(struct.unpack_from("<f", self.d, ofs + 64 * i + 48)[0]) > 0.5
                   for i in range(count))

    def meshes_by_part(self, model: int) -> Dict[int, List[int]]:
        parts: Dict[int, List[int]] = {}
        o = model + _i32(self.d, model + MODEL_MESH_OFS)
        for _ in range(_i32(self.d, model + MODEL_MESH_COUNT)):
            if o + MESH_MIN > len(self.d):
                break
            size = _u32(self.d, o)
            if not MESH_MIN <= size <= MESH_MAX or o + size > len(self.d):
                break
            parts.setdefault(self.d[o + MESH_PART], []).append(o)
            o += size
        return parts

    def mesh_triangles(self, o: int) -> List[Tuple[Tuple[float, float], ...]]:
        """Triangles of one mesh as (x, z) map points (z = north, as on the pause map)."""
        size = _u32(self.d, o)
        q, blocks, tris = 0x50, [], []
        while q + 4 <= size:
            w = _u32(self.d, o + q)
            cmd, num, imm = (w >> 24) & 0x7F, (w >> 16) & 0xFF, w & 0xFFFF
            q += 4
            if cmd & 0x60 == 0x60:   # UNPACK: vn = components - 1, vl = width
                vn, vl, addr = (cmd >> 2) & 3, cmd & 3, imm & 0x3FF
                num = num or 256
                nbytes = 2 * num if vl == 3 else (vn + 1) * (4 >> vl) * num
                nbytes = (nbytes + 3) & ~3
                if q + nbytes > size:
                    break
                if cmd == VIF_UNPACK_V3_32:
                    blocks.append((o + q, addr, num))
                elif cmd == VIF_UNPACK_V4_16 and addr > 0x10 and blocks:
                    tris += self._strip(struct.unpack_from(f"<{4 * num}H", self.d, o + q), blocks)
                    blocks = []   # the next batch uploads its own vertices
                q += nbytes
            elif cmd in (0x50, 0x51):   # DIRECT / DIRECTHL
                q += 16 * imm
            elif cmd in (0x30, 0x31):   # STROW / STCOL
                q += 16
            elif cmd == 0x20:           # STMASK
                q += 4
        return tris

    def _strip(self, idx: Sequence[int], blocks) -> list:
        """Triangle strip: entry k (bit 15 clear, k >= 2) draws k-2, k-1, k."""
        out, window = [], []
        for e in idx:
            a, v = e & 0x7FFF, None
            for data, addr, num in blocks:
                off = a - addr
                if off >= 0 and not off & 3 and off // 4 < num:
                    x, _y, z = struct.unpack_from("<3i", self.d, data + 12 * (off // 4))
                    v = (x / 16.0, -z / 16.0)
                    break
            if v is None:   # not a vertex of this batch: restart the strip
                window = []
                continue
            if len(window) >= 2 and not e & 0x8000:
                out.append((window[-2], window[-1], v))
            window = (window + [v])[-2:]
        return out


def local_to_map(piece: dict, x: float, z: float) -> Tuple[float, float]:
    c, s = math.cos(piece["yaw"]), math.sin(piece["yaw"])
    px, _py, pz = piece["pos"]
    return px + c * x + s * z, pz - s * x + c * z


def world_to_map(piece: dict, wx: float, wz: float) -> Tuple[float, float]:
    """Room (world) coordinates -> pause map, as the pause map marker (0x6C3EB8)."""
    c, s = math.cos(piece["yaw"]), math.sin(piece["yaw"])
    sx, _sy, sz = piece["scale"]
    x, z = wx * 0.1, wz * 0.1
    px, _py, pz = piece["pos"]
    return px + sx * (c * x + s * z), pz + sz * (-s * x + c * z)


def build_area(data: bytes, base: int) -> Tuple[bytes, List[dict], bool]:
    """Decode a map file: (triangles as float32 x, z pairs, 3 per triangle; pieces with their
    "walls"/"floors" [start, count] triangle ranges and "box"; meshes were room-local)."""
    mf = MapFile(data, base)
    pieces = mf.pieces()
    model = mf.model()
    local = mf.parts_local(model)
    by_part = mf.meshes_by_part(model)
    out: List[float] = []
    count = 0
    for p in pieces:
        first = count
        for kind in ("walls", "floors"):
            start = count
            for part in p["wall_parts" if kind == "walls" else "floor_parts"]:
                for mesh in by_part.get(part, []):
                    for tri in mf.mesh_triangles(mesh):
                        for x, z in tri:
                            if local:
                                x, z = local_to_map(p, x, z)
                            out += (x, z)
                        count += 1
            p[kind] = [start, count - start]
        if count > first:
            xs, zs = out[6 * first::2], out[6 * first + 1::2]
            p["box"] = [min(xs), min(zs), max(xs), max(zs)]
        p["save"] = bool(p["flags"] & PIECE_FLAG_SAVE)
        del p["wall_parts"], p["floor_parts"]
    return struct.pack(f"<{len(out)}f", *out), pieces, local


# ---- Leon's piece ----

def current_piece(pieces: Sequence[dict], stage: int, room: int, leon_y: float,
                  floor_height: float) -> Optional[dict]:
    """The piece Map_GetCurrentPiece (0x6C0E90) picks for Leon."""
    mine = [p for p in pieces if p["stage"] == stage and p["room"] == room]
    if len(mine) < 2:
        return mine[0] if mine else None
    lowest = min(p["floor"] for p in mine)
    if floor_height > 0 and math.isfinite(leon_y):
        level = int(abs(leon_y) / floor_height)
    else:
        level = len(mine) - 1   # a zero height divides to +inf on the PS2: clamped to the top
    level = max(0, min(level, len(mine) - 1))
    for p in mine:   # the game returns nothing when no piece sits on that floor
        if p["floor"] == lowest + level:
            return p
    return None


# ---- live reads ----

def read_room_table(mem: Memory) -> Tuple[List[int], List[int]]:
    """(first room key per stage, room count per stage); empty before the table is loaded."""
    table = _word(mem, ROOM_TABLE_PTR)
    if not in_ram(table):
        return [], []
    head = mem.read(table, 0x10)
    stages = struct.unpack_from("<h", head, 0)[0]
    if not 0 < stages <= 32:
        return [], []
    counts = list(struct.unpack(f"<{stages}i", mem.read(_u32(head, 0x08), 4 * stages)))
    first = list(struct.unpack(f"<{stages}i", mem.read(_u32(head, 0x0C), 4 * stages)))
    return first, counts


def read_floor_heights(mem: Memory, stages: int) -> List[float]:
    return list(struct.unpack(f"<{stages}f", mem.read(FLOOR_HEIGHTS, 4 * stages)))


def read_visited(mem: Memory) -> List[int]:
    table, count = struct.unpack("<2I", mem.read(ROOM_STATE_PTR, 8))
    if not in_ram(table) or not 0 < count <= 1024:
        return []
    words = struct.unpack(f"<{3 * count}I", mem.read(table, 12 * count))
    return [words[3 * k] & 1 for k in range(count)]


def read_leon(mem: Memory) -> dict:
    stage, room = struct.unpack("<2H", mem.read(CUR_STAGE, 4))
    x, y, z = struct.unpack("<3f", mem.read(PLAYER_POS, 12))
    model = _word(mem, PLAYER_MODEL)
    yaw = struct.unpack("<f", mem.read(model + MODEL_YAW, 4))[0] if in_ram(model) else 0.0
    file_id, file_ptr = struct.unpack("<iI", mem.read(MAP_FILE_ID, 8))
    roomdata = _word(mem, ROOMDATA)
    return {"stage": stage, "room": room, "x": x, "y": y, "z": z, "yaw": yaw,
            "map_file_id": file_id, "map_file": file_ptr, "roomdata": roomdata}


def read_doors(mem: Memory, roomdata: int) -> List[dict]:
    """The loaded room's door records (ROOMDATA object list 0) with a destination."""
    lists = _word(mem, roomdata + ROOMDATA_OBJLISTS)
    if not in_ram(lists):
        return []
    list0 = _word(mem, lists + 4)
    if not in_ram(list0):
        return []
    count = _i32(mem.read(list0, 4))
    if not 0 <= count <= 64:
        return []
    recs = mem.read(list0 + 0x10, OBJ_REC * count) if count else b""
    doors = []
    for i in range(count):
        rec = recs[OBJ_REC * i:OBJ_REC * (i + 1)]
        dest_stage, dest_room = struct.unpack_from("<2h", rec, DOOR_DEST)
        if dest_stage < 0 or dest_room < 0:
            continue
        x, _y, z = struct.unpack_from("<3f", rec, 0)
        doors.append({"x": x, "z": z, "dest": [dest_stage, dest_room]})
    return doors
