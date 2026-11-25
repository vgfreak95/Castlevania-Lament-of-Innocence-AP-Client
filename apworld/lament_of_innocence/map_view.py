"""The map tracker as a tab in the client window: a 2D top-down view of the same data the web
page (data/tracker/index.html) shows, read straight from the MapTracker with no HTTP.

Kivy only: import this from make_gui, never at module level (the tests and the CLI run without it).

Map space is the pause map's: x right, z north, so z maps straight onto screen y.
"""
from __future__ import annotations

import math
from array import array
from typing import Dict, List, Optional, Tuple

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, InstructionGroup, Line, Mesh, PopMatrix, PushMatrix, Rectangle, Scale, \
    Translate, Triangle, Ellipse
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.stencilview import StencilView
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

from .tracker import MapTracker

UPDATE_INTERVAL = 0.25
MAX_MESH_TRIS = 20000          # Kivy mesh indices are 16-bit
MIN_SCALE, MAX_SCALE = 0.005, 40.0


def _rgb(hex_color: int, alpha: float = 1.0) -> Tuple[float, float, float, float]:
    return ((hex_color >> 16) / 255, (hex_color >> 8 & 0xFF) / 255, (hex_color & 0xFF) / 255, alpha)


COL = {
    "bg": 0x0D0F14, "visited": 0x4F7FBF, "unvisited": 0x3A3F4C, "done": 0x3F9A55, "save": 0xB04848,
    "here": 0x7FD0D8, "door": 0xE0C040, "left": 0xF08A30, "player": 0xFFD75A, "checked": 0x6A6F7A,
    "wall": 0x9AA3B5, "wall_here": 0xD8F0F4, "wall_unvisited": 0x555A66,
}
OTHER_FLOOR_ALPHA = 0.25       # floors other than the shown one, when showing all floors


def _point_in_tri(px: float, pz: float, t, o: int) -> bool:
    ax, az, bx, bz, cx, cz = t[o], t[o + 1], t[o + 2], t[o + 3], t[o + 4], t[o + 5]
    d1 = (px - bx) * (az - bz) - (ax - bx) * (pz - bz)
    d2 = (px - cx) * (bz - cz) - (bx - cx) * (pz - cz)
    d3 = (px - ax) * (cz - az) - (cx - ax) * (pz - az)
    neg = d1 < 0 or d2 < 0 or d3 < 0
    pos = d1 > 0 or d2 > 0 or d3 > 0
    return not (neg and pos)


class _Room:
    """One map piece: its floor and wall meshes, each behind its own Color."""

    def __init__(self, piece: dict, tris: array):
        self.piece = piece
        self.floor_color = Color(*_rgb(COL["visited"]))
        self.wall_color = Color(*_rgb(COL["wall"]))
        self.group = InstructionGroup()
        self.group.add(self.floor_color)
        for mesh in self._meshes(tris, *piece["floors"]):
            self.group.add(mesh)
        self.group.add(self.wall_color)
        for mesh in self._meshes(tris, *piece["walls"]):
            self.group.add(mesh)

    @staticmethod
    def _meshes(tris: array, start: int, count: int) -> List[Mesh]:
        out = []
        for first in range(start, start + count, MAX_MESH_TRIS):
            n = min(MAX_MESH_TRIS, start + count - first)
            verts = []
            for i in range(first * 6, (first + n) * 6, 2):
                verts += (tris[i], tris[i + 1], 0.0, 0.0)
            out.append(Mesh(vertices=verts, indices=list(range(n * 3)), mode="triangles"))
        return out

    def contains(self, tris: array, x: float, z: float) -> bool:
        box = self.piece.get("box")
        if not box or not (box[0] <= x <= box[2] and box[1] <= z <= box[3]):
            return False
        for kind in ("floors", "walls"):
            start, count = self.piece[kind]
            for i in range(start, start + count):
                if _point_in_tri(x, z, tris, i * 6):
                    return True
        return False


class MapCanvas(StencilView):
    """Draws one area; pan by dragging, zoom with the mouse wheel, click a room for its locations."""

    def __init__(self, view: "MapTab", **kwargs):
        super().__init__(**kwargs)
        self.view = view
        self.scale_ = 1.0                       # pixels per map unit
        self.center_map = (0.0, 0.0)            # map point at the widget's centre
        self.rooms: List[_Room] = []
        self.tris = array("f")
        self.down: Optional[Tuple[float, float]] = None
        self.dragged = False
        with self.canvas.before:
            Color(*_rgb(COL["bg"]))
            self.bg = Rectangle(pos=self.pos, size=self.size)
        with self.canvas:
            PushMatrix()
            self.translate = Translate()
            self.scale_instr = Scale(1, 1, 1)
        self.world = InstructionGroup()
        self.canvas.add(self.world)
        self.canvas.add(PopMatrix())
        self.markers = InstructionGroup()       # screen space: sizes stay put while zooming
        self.canvas.add(self.markers)
        self.top_floor: Optional[int] = -999    # the floor whose rooms are drawn last
        self.bind(pos=self._on_resize, size=self._on_resize)
        Window.bind(mouse_pos=self._on_mouse_pos)

    # ---- view transform ----
    def _on_resize(self, *_args) -> None:
        self.bg.pos, self.bg.size = self.pos, self.size
        if self.view.fit_pending:
            self.view.fit_area()
        self.apply_view()

    def to_screen(self, x: float, z: float) -> Tuple[float, float]:
        cx, cz = self.center_map
        return self.center_x + (x - cx) * self.scale_, self.center_y + (z - cz) * self.scale_

    def to_map(self, sx: float, sy: float) -> Tuple[float, float]:
        cx, cz = self.center_map
        return cx + (sx - self.center_x) / self.scale_, cz + (sy - self.center_y) / self.scale_

    def apply_view(self) -> None:
        cx, cz = self.center_map
        self.translate.xy = (self.center_x - cx * self.scale_, self.center_y - cz * self.scale_)
        self.scale_instr.xyz = (self.scale_, self.scale_, 1)
        self.view.draw_markers()

    def fit(self, boxes: List[List[float]]) -> None:
        if not boxes:
            return
        x0, z0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, z1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        self.center_map = ((x0 + x1) / 2, (z0 + z1) / 2)
        w, h = max(x1 - x0, 1.0), max(z1 - z0, 1.0)
        self.scale_ = max(MIN_SCALE, min(MAX_SCALE, 0.9 * min(self.width / w, self.height / h)))
        self.apply_view()

    def zoom(self, factor: float, sx: float, sy: float) -> None:
        before = self.to_map(sx, sy)
        self.scale_ = max(MIN_SCALE, min(MAX_SCALE, self.scale_ * factor))
        after = self.to_map(sx, sy)
        cx, cz = self.center_map
        self.center_map = (cx + before[0] - after[0], cz + before[1] - after[1])
        self.apply_view()

    # ---- area ----
    def load(self, tris: array, pieces: List[dict]) -> None:
        self.tris = tris
        self.rooms = [_Room(p, tris) for p in sorted(pieces, key=lambda p: p["floor"])
                      if p["floors"][1] or p["walls"][1]]
        self.top_floor = -999
        self.order(None)

    def order(self, top: Optional[int]) -> None:
        """Draw lower floors first, so upper ones cover them, and floor `top` (if any) above all."""
        if top == self.top_floor:
            return
        self.top_floor = top
        self.rooms.sort(key=lambda r: (r.piece["floor"] == top, r.piece["floor"]))
        self.world.clear()
        for room in self.rooms:
            self.world.add(room.group)

    def room_at(self, sx: float, sy: float) -> Optional[_Room]:
        x, z = self.to_map(sx, sy)
        for room in reversed(self.rooms):       # topmost drawn first
            if self.view.room_shown(room) and room.contains(self.tris, x, z):
                return room
        return None

    # ---- input ----
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if touch.is_mouse_scrolling:
            factor = 1.2 if touch.button == "scrolldown" else 1 / 1.2
            self.zoom(factor, *touch.pos)
            return True
        if touch.is_double_tap:
            self.view.fit_area()
            return True
        touch.grab(self)
        self.down, self.dragged = touch.pos, False
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False
        if not self.dragged and math.dist(touch.pos, self.down) > dp(4):
            self.dragged = True
            self.view.set_follow(False)
        if self.dragged:
            cx, cz = self.center_map
            self.center_map = (cx - touch.dx / self.scale_, cz - touch.dy / self.scale_)
            self.apply_view()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        if not self.dragged:
            self.view.pick(*touch.pos)
        return True

    def _on_mouse_pos(self, _window, pos) -> None:
        if self.get_root_window() is None:
            return
        local = self.to_widget(*pos)
        self.view.hover(local if self.collide_point(*local) else None)


class MapTab(BoxLayout):
    """Controls on top, the map in the middle, status and the clicked room's details below."""

    def __init__(self, tracker: MapTracker, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.tracker = tracker
        self.maps: dict = {"areas": []}
        self.state: dict = {}
        self.version = -1
        self.area: Optional[dict] = None
        self.follow = True
        self.selected: Optional[_Room] = None
        self.picked_text = ""
        self.fit_pending = True

        bar = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(4), padding=(dp(4), dp(2)))
        self.area_spin = Spinner(text="No map yet", values=[], size_hint_x=None, width=dp(190))
        self.area_spin.bind(text=self._on_area_pick)
        self.floor_spin = Spinner(text="Leon's floor", values=["Leon's floor", "All floors"],
                                  size_hint_x=None, width=dp(120))
        self.floor_spin.bind(text=lambda *_: self.refresh())
        bar.add_widget(self.area_spin)
        bar.add_widget(self.floor_spin)
        self.toggles: Dict[str, ToggleButton] = {}
        for key, label in (("follow", "Follow"), ("unvisited", "Unvisited"), ("doors", "Doors"),
                           ("torches", "Torches")):
            btn = ToggleButton(text=label, state="down", size_hint_x=None, width=dp(84))
            btn.bind(state=self._on_toggle)
            self.toggles[key] = btn
            bar.add_widget(btn)
        fit = Button(text="Fit", size_hint_x=None, width=dp(56))
        fit.bind(on_release=lambda *_: self.fit_area())
        bar.add_widget(fit)
        bar.add_widget(Widget())
        self.add_widget(bar)

        self.canvas_view = MapCanvas(self)
        self.add_widget(self.canvas_view)

        self.status = Label(size_hint_y=None, height=dp(22), halign="left", valign="middle",
                            markup=True, padding=(dp(8), 0))
        self.status.bind(size=lambda lbl, size: setattr(lbl, "text_size", size))
        self.add_widget(self.status)
        self.info = Label(size_hint_y=None, height=dp(0), halign="left", valign="top", markup=True,
                          padding=(dp(8), dp(4)))
        self.info.bind(size=lambda lbl, size: setattr(lbl, "text_size", size))
        self.add_widget(self.info)

        Clock.schedule_interval(self.update, UPDATE_INTERVAL)
        Clock.schedule_once(self.update, 0)

    # ---- options ----
    def opt(self, key: str) -> bool:
        return self.toggles[key].state == "down"

    def _on_toggle(self, btn: ToggleButton, state: str) -> None:
        if btn is self.toggles["follow"]:
            self.follow = state == "down"
        self.refresh()

    def set_follow(self, on: bool) -> None:
        self.toggles["follow"].state = "down" if on else "normal"

    def _area_label(self, area: dict) -> str:
        return f"Area {area['id']} (stage {', '.join(map(str, area['stages']))})"

    def _on_area_pick(self, _spinner, text: str) -> None:
        area = next((a for a in self.maps["areas"] if self._area_label(a) == text), None)
        if area and (not self.area or area["id"] != self.area["id"]):
            if self.state.get("area") != area["id"]:
                self.set_follow(False)
            self.load_area(area)

    # ---- data ----
    def room_key(self, stage: int, room: int) -> int:
        fk = self.state.get("first_keys") or []
        return fk[stage] + room if stage < len(fk) else -1

    def visited(self, stage: int, room: int) -> bool:
        key, seen = self.room_key(stage, room), self.state.get("visited") or []
        return 0 <= key < len(seen) and bool(seen[key])

    def locations(self, stage: int, room: int) -> List[list]:
        return (self.state.get("rooms") or {}).get(str(self.room_key(stage, room)), [])

    def leon_here(self) -> Optional[dict]:
        p = self.state.get("player")
        return p if p and self.area and self.state.get("area") == self.area["id"] else None

    def shown_floor(self) -> Optional[int]:
        """The floor drawn at full strength: Leon's (when he's in this area), else all."""
        if self.floor_spin.text.startswith("Floor "):
            return int(self.floor_spin.text[6:])
        if self.floor_spin.text == "Leon's floor":
            leon = self.leon_here()
            return leon["floor"] if leon else None
        return None

    def room_shown(self, room: _Room) -> bool:
        p = room.piece
        if self.floor_spin.text.startswith("Floor ") and p["floor"] != self.shown_floor():
            return False
        return self.opt("unvisited") or self.visited(p["stage"], p["room"]) or self.is_here(p)

    def is_here(self, p: dict) -> bool:
        return (self.leon_here() is not None and self.state.get("stage") == p["stage"]
                and self.state.get("room") == p["room"])

    def load_area(self, area: dict, frame: bool = True) -> None:
        raw = self.tracker.area_bin(area["id"])
        if raw is None:
            return
        tris = array("f")
        tris.frombytes(raw)
        self.area = area
        self.selected = None
        self.canvas_view.load(tris, area["pieces"])
        floors = sorted({p["floor"] for p in area["pieces"]})
        self.floor_spin.values = ["Leon's floor", "All floors"] + [f"Floor {f}" for f in floors]
        if self.floor_spin.text not in self.floor_spin.values:
            self.floor_spin.text = "Leon's floor"
        self.area_spin.text = self._area_label(area)
        self.refresh()
        if frame:
            self.fit_area()

    def fit_area(self) -> None:
        # the tab is laid out only once it's first shown: fit again then
        self.fit_pending = self.canvas_view.get_root_window() is None
        if self.area:
            self.canvas_view.fit([r.piece["box"] for r in self.canvas_view.rooms if r.piece.get("box")])

    def update(self, *_args) -> None:
        self.state = self.tracker.snapshot()
        if self.state.get("version") != self.version:
            self.version = self.state.get("version")
            self.maps = self.tracker.maps()
            self.area_spin.values = [self._area_label(a) for a in self.maps["areas"]]
            if self.area:   # its shapes may have changed: reload it, keeping the view
                self.area = next((a for a in self.maps["areas"] if a["id"] == self.area["id"]), None)
                if self.area:
                    self.load_area(self.area, frame=False)
        ids = {a["id"]: a for a in self.maps["areas"]}
        leon_area = self.state.get("area")
        if leon_area in ids and (not self.area or (self.follow and self.area["id"] != leon_area)):
            self.load_area(ids[leon_area])
        elif not self.area and self.maps["areas"]:
            self.load_area(self.maps["areas"][0])
        if self.follow and self.leon_here():
            p = self.leon_here()
            self.canvas_view.center_map = (p["x"], p["z"])
            self.canvas_view.apply_view()
        self.refresh()

    # ---- drawing ----
    def refresh(self) -> None:
        """Room colours and visibility, markers and the status line, from the last state."""
        shown = self.shown_floor()
        all_floors = self.floor_spin.text == "All floors"
        self.canvas_view.order(None if all_floors else shown)
        for room in self.canvas_view.rooms:
            p = room.piece
            seen, here = self.visited(p["stage"], p["room"]), self.is_here(p)
            locs = self.locations(p["stage"], p["room"])
            left = sum(1 for _n, checked in locs if not checked)
            if not self.room_shown(room):
                room.floor_color.a = room.wall_color.a = 0
                continue
            fill = (COL["here"] if here else COL["save"] if p["save"] else COL["done"] if locs and not left
                    else COL["visited"] if seen else COL["unvisited"])
            wall = COL["wall_here"] if here else COL["wall"] if seen else COL["wall_unvisited"]
            alpha = 1.0 if seen or here else 0.45
            if shown is not None and not all_floors and p["floor"] != shown:
                alpha *= OTHER_FLOOR_ALPHA
            room.floor_color.rgba = _rgb(fill, alpha)
            room.wall_color.rgba = _rgb(wall, alpha)
        self.draw_markers()
        self.show_status()

    def _marker_visible(self, floor: int) -> bool:
        shown = self.shown_floor()
        return shown is None or self.floor_spin.text == "All floors" or floor == shown

    def draw_markers(self) -> None:
        cv = self.canvas_view
        group = cv.markers
        group.clear()
        if not self.area:
            return
        r = dp(4)
        for room in cv.rooms:
            p = room.piece
            if p.get("box") and self.room_shown(room) and self._marker_visible(p["floor"]):
                left = sum(1 for _n, checked in self.locations(p["stage"], p["room"]) if not checked)
                if left:
                    x0, z0, x1, z1 = p["box"]
                    sx, sy = cv.to_screen((x0 + x1) / 2, (z0 + z1) / 2)
                    if cv.collide_point(sx, sy):
                        group.add(Color(*_rgb(COL["left"])))
                        group.add(Triangle(points=[sx, sy + r * 1.6, sx - r * 1.3, sy - r, sx + r * 1.3, sy - r]))
        if self.opt("doors"):
            group.add(Color(*_rgb(COL["door"])))
            for d in self.state.get("doors") or []:
                if d["area"] == self.area["id"] and self._marker_visible(d["floor"]):
                    sx, sy = cv.to_screen(d["x"], d["z"])
                    if cv.collide_point(sx, sy):
                        group.add(Rectangle(pos=(sx - r * 0.8, sy - r * 0.8), size=(r * 1.6, r * 1.6)))
        if self.opt("torches"):
            for t in self.state.get("torches") or []:
                if t["area"] == self.area["id"] and self._marker_visible(t["floor"]):
                    sx, sy = cv.to_screen(t["x"], t["z"])
                    if cv.collide_point(sx, sy):
                        group.add(Color(*_rgb(COL["checked"] if t["checked"] else COL["left"])))
                        group.add(Ellipse(pos=(sx - r, sy - r), size=(r * 2, r * 2)))
        if self.selected and self.selected.piece.get("box"):
            x0, z0, x1, z1 = self.selected.piece["box"]
            ax, ay = cv.to_screen(x0, z0)
            bx, by = cv.to_screen(x1, z1)
            group.add(Color(1, 1, 1, 0.8))
            group.add(Line(rectangle=(ax, ay, bx - ax, by - ay), width=1))
        leon = self.leon_here()
        if leon:
            sx, sy = cv.to_screen(leon["x"], leon["z"])
            dx, dz = leon["dir"]
            size = dp(11)
            tip = (sx + dx * size, sy + dz * size)
            left = (sx - dx * size * 0.6 - dz * size * 0.6, sy - dz * size * 0.6 + dx * size * 0.6)
            right = (sx - dx * size * 0.6 + dz * size * 0.6, sy - dz * size * 0.6 - dx * size * 0.6)
            group.add(Color(0, 0, 0, 0.7))
            group.add(Line(points=[*tip, *left, *right], close=True, width=dp(1.5)))
            group.add(Color(*_rgb(COL["player"])))
            group.add(Triangle(points=[*tip, *left, *right]))

    def show_status(self) -> None:
        s = self.state
        if s.get("connected"):
            txt = f"[color=5fbf75]PCSX2[/color] · stage [b]{s.get('stage')}[/b] room [b]{s.get('room')}[/b]"
            if s.get("player"):
                txt += f" · floor [b]{s['player']['floor']}[/b]"
        else:
            txt = "[color=d76060]PCSX2 not connected[/color]"
        if s.get("slot"):
            all_locs = [loc for locs in (s.get("rooms") or {}).values() for loc in locs]
            done = sum(1 for _n, checked in all_locs if checked)
            txt += f"   ·   {_esc(s['slot'])}: {done} of {len(all_locs)} pickups checked"
        if not self.maps["areas"]:
            txt += "   ·   No map yet: each area appears once Leon has been in it while connected."
        elif self.picked_text:
            txt += f"   ·   {self.picked_text}"
        self.status.text = txt

    # ---- picking ----
    def hover(self, pos: Optional[Tuple[float, float]]) -> None:
        room = self.canvas_view.room_at(*pos) if pos and self.area else None
        text = ""
        if room:
            p = room.piece
            text = f"stage {p['stage']} room {p['room']}"
        if text != self.picked_text:
            self.picked_text = text
            self.show_status()

    def pick(self, sx: float, sy: float) -> None:
        cv = self.canvas_view
        lines: List[str] = []
        if self.area and self.opt("torches"):
            for t in self.state.get("torches") or []:
                if t["area"] == self.area["id"] and self._marker_visible(t["floor"]) \
                        and math.dist(cv.to_screen(t["x"], t["z"]), (sx, sy)) < dp(7):
                    lines.append(f"[b]{_esc(t['name'])}[/b] · {'checked' if t['checked'] else 'not checked'}")
        room = cv.room_at(sx, sy) if self.area else None
        self.selected = room
        if room:
            p = room.piece
            head = f"[b]Stage {p['stage']}, room {p['room']}[/b] · floor {p['floor']}"
            if p["save"]:
                head += " · save room"
            head += " · " + ("visited" if self.visited(p["stage"], p["room"]) else "not visited")
            lines.append(head)
            for name, checked in self.locations(p["stage"], p["room"]):
                lines.append(f"[color=8a90a0][s]{_esc(name)}[/s][/color]" if checked
                             else f"  • {_esc(name)}")
        self.info.text = "\n".join(lines)
        self.info.height = dp(8) + dp(18) * len(lines) if lines else 0
        self.draw_markers()


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def build_map_tab(tracker: MapTracker) -> MapTab:
    tracker.enabled = True
    return MapTab(tracker)
