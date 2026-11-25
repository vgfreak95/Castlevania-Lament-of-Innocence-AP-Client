"""Unit tests for the map tracker (apworld/lament_of_innocence/mapshapes.py, tracker.py), run
against an in-memory fake of the game's RAM: a synthetic pause map file, room table, floor
heights, visited table and door records.

usage: py -3.13 tools/test_map_tracker.py [-v]
"""
import importlib.util
import json
import os
import struct
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "apworld", "lament_of_innocence")

# a stand-in for the world package (its __init__ needs Archipelago), so the relative import in
# tracker.py and pkgutil.get_data(data/tracker/index.html) work
_spec = importlib.util.spec_from_file_location("loi_map", os.path.join(PKG, "__init__.py"),
                                               submodule_search_locations=[PKG])
sys.modules["loi_map"] = importlib.util.module_from_spec(_spec)


def _load(name):
    spec = importlib.util.spec_from_file_location(f"loi_map.{name}", os.path.join(PKG, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ms = _load("mapshapes")
tracker = _load("tracker")

RAM_SIZE = 0x02000000
MAP_BASE = 0x01000000
FILE_ID = 42
SQUARE = [(0, 0), (160, 0), (0, 160), (160, 160)]   # model units (x, z); / 16 on the map
# (stage, room, floor): room 5 has two floors
PIECES = [(2, 5, 0), (2, 5, 1), (2, 6, 0)]
PIECE_POS = (100.0, 0.0, 200.0)


class FakeRam:
    def __init__(self):
        self.ram = bytearray(RAM_SIZE)
        self.reads = 0

    def read(self, addr, length):
        self.reads += 1
        assert 0 <= addr and addr + length <= RAM_SIZE, hex(addr)
        return bytes(self.ram[addr:addr + length])

    def put(self, addr, fmt, *values):
        struct.pack_into(fmt, self.ram, addr, *values)


def build_map_file(ram: FakeRam, base=MAP_BASE) -> int:
    """A pause map file: PIECES, then a model with one wall mesh and one floor mesh per piece,
    each a 4-entry strip (two triangles over SQUARE). Returns its length."""
    ram.put(base, "<2I", 1, len(PIECES))
    pieces_at = base + 0x100
    for i, (stage, room, floor) in enumerate(PIECES):
        p = pieces_at + 0x60 * i
        ram.put(base + 0x30 + 4 * i, "<I", p)
        ram.put(p, "<BBb", stage, room, floor)
        ram.put(p + 0x10, "<5H", 1, 1, 0, 0, 0)
        ram.put(p + 0x1A, "<B", 2 * i)          # wall part
        ram.put(p + 0x1E, "<B", 2 * i + 1)      # floor part
        ram.put(p + 0x40, "<4f", *PIECE_POS, 0.0)
        ram.put(p + 0x50, "<3f", 1.0, 1.0, 1.0)
    model = (pieces_at + 0x60 * len(PIECES) + 15) & ~15
    ram.put(model, "<I", 0xFFFF0001)
    ram.put(model + 0x08, "<2i", 0x30, 0)        # no part matrices
    n_meshes = 2 * len(PIECES)
    ram.put(model + 0x20, "<2i", n_meshes, 0x40)
    mesh = model + 0x40
    for part in range(n_meshes):
        size = 0x50 + 4 + 12 * 4 + 4 + 8
        ram.put(mesh, "<I", size)
        ram.put(mesh + 0x43, "<B", part)
        q = mesh + 0x50
        ram.put(q, "<I", (0x68 << 24) | (4 << 16) | 0)        # UNPACK V3-32, 4 vertices @ 0
        for k, (x, z) in enumerate(SQUARE):
            ram.put(q + 4 + 12 * k, "<3i", x, 0, z)
        q += 4 + 48
        ram.put(q, "<I", (0x6D << 24) | (1 << 16) | 0x20)      # UNPACK V4-16, 4 indices
        ram.put(q + 4, "<4H", 0 | 0x8000, 4 | 0x8000, 8, 12)
        mesh += size
    return mesh - base


def build_game(ram: FakeRam, leon=(1000.0, -2500.0, 500.0), stage=2, room=5):
    build_map_file(ram)
    ram.put(ms.MAP_FILE_ID, "<iI", FILE_ID, MAP_BASE)
    ram.put(ms.CUR_STAGE, "<2H", stage, room)
    ram.put(ms.PLAYER_POS, "<3f", *leon)
    ram.put(ms.PLAYER_MODEL, "<I", 0x01100000)
    ram.put(0x01100000 + ms.MODEL_YAW, "<f", 0.0)
    # room table: 3 stages of 10 rooms, keys 0, 10, 20
    table = 0x01200000
    ram.put(ms.ROOM_TABLE_PTR, "<I", table)
    ram.put(table, "<hh3I", 3, 1, 0, table + 0x20, table + 0x40)
    ram.put(table + 0x20, "<3i", 10, 10, 10)
    ram.put(table + 0x40, "<3i", 0, 10, 20)
    ram.put(ms.FLOOR_HEIGHTS, "<3f", 2000.0, 2000.0, 2000.0)
    # visited: room key 25 (stage 2 room 5)
    states = 0x01300000
    ram.put(ms.ROOM_STATE_PTR, "<2I", states, 30)
    ram.put(states + 12 * 25, "<I", 1)
    # ROOMDATA: object list 0 with one door to stage 2 room 6 and one record without a destination
    rd, lists, list0 = 0x01400000, 0x01400100, 0x01400200
    ram.put(ms.ROOMDATA, "<I", rd)
    ram.put(rd + 4, "<I", lists)
    ram.put(lists + 4, "<I", list0)
    ram.put(list0, "<i", 2)
    ram.put(list0 + 0x10, "<3f", 300.0, 0.0, 400.0)
    ram.put(list0 + 0x10 + 0x50, "<4h", 2, 6, 0, 0)
    ram.put(list0 + 0x90 + 0x50, "<4h", -1, -1, 0, 0)


class DecodeTests(unittest.TestCase):
    def test_extent_and_decode(self):
        ram = FakeRam()
        length = build_map_file(ram)
        self.assertEqual(ms.map_file_extent(ram, MAP_BASE), length)
        tris, pieces, local = ms.build_area(ms.copy_map_file(ram, MAP_BASE), MAP_BASE)
        self.assertFalse(local)
        # 2 meshes per piece, 2 triangles each, 3 corners of float32 x, z
        self.assertEqual(len(tris), 2 * len(PIECES) * 2 * 3 * 2 * 4)
        self.assertEqual([p["walls"] for p in pieces], [[0, 2], [4, 2], [8, 2]])
        self.assertEqual([p["floors"] for p in pieces], [[2, 2], [6, 2], [10, 2]])
        self.assertEqual(pieces[0]["box"], [0.0, -10.0, 10.0, 0.0])   # z flipped, / 16
        first = struct.unpack("<6f", tris[:24])
        self.assertEqual(first, (0.0, 0.0, 10.0, 0.0, 0.0, -10.0))

    def test_not_relocated(self):
        ram = FakeRam()
        build_map_file(ram)
        ram.put(MAP_BASE, "<I", 0)
        with self.assertRaises(ms.MapShapeError):
            ms.map_file_extent(ram, MAP_BASE)

    def test_bad_pointer(self):
        ram = FakeRam()
        build_map_file(ram)
        data = bytearray(ms.copy_map_file(ram, MAP_BASE))
        struct.pack_into("<I", data, 0x30, 0x10)
        with self.assertRaises(ms.MapShapeError):
            ms.build_area(bytes(data), MAP_BASE)


class PlacementTests(unittest.TestCase):
    def setUp(self):
        ram = FakeRam()
        build_map_file(ram)
        _tris, self.pieces, _local = ms.build_area(ms.copy_map_file(ram, MAP_BASE), MAP_BASE)

    def floor(self, y, height=2000.0, room=5):
        return ms.current_piece(self.pieces, 2, room, y, height)["floor"]

    def test_floor_from_height(self):
        self.assertEqual(self.floor(0.0), 0)
        self.assertEqual(self.floor(-1999.0), 0)
        self.assertEqual(self.floor(-2500.0), 1)
        self.assertEqual(self.floor(2500.0), 1)          # |y|
        self.assertEqual(self.floor(-99999.0), 1)        # clamped to the room's pieces
        self.assertEqual(self.floor(-10.0, height=0.0), 1)   # 0 divides to +inf on the PS2

    def test_single_and_missing(self):
        self.assertEqual(self.floor(-99999.0, room=6), 0)
        self.assertIsNone(ms.current_piece(self.pieces, 2, 7, 0.0, 2000.0))

    def test_world_to_map(self):
        p = dict(pos=[100.0, 0.0, 200.0], yaw=0.0, scale=[1.0, 1.0, 1.0])
        self.assertEqual(ms.world_to_map(p, 1000.0, 500.0), (200.0, 250.0))
        p["yaw"] = 3.141592653589793 / 2
        x, z = ms.world_to_map(p, 1000.0, 0.0)
        self.assertAlmostEqual(x, 100.0, places=4)
        self.assertAlmostEqual(z, 100.0, places=4)


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "maps"

    def tearDown(self):
        self.tmp.cleanup()

    def test_capture_place_and_cache(self):
        ram = FakeRam()
        build_game(ram)
        t = tracker.MapTracker(self.cache)
        t.tick(ram)
        self.assertEqual(t.areas, {})        # waits to see the same file twice
        t.tick(ram)
        self.assertIn(FILE_ID, t.areas)
        state = t.snapshot()
        self.assertTrue(state["connected"])
        self.assertEqual(state["player"]["floor"], 1)
        self.assertAlmostEqual(state["player"]["x"], 200.0, places=4)
        self.assertAlmostEqual(state["player"]["z"], 250.0, places=4)
        self.assertEqual(state["player"]["dir"], [0.0, 1.0])
        self.assertEqual(state["first_keys"], [0, 10, 20])
        self.assertEqual(state["visited"][25], 1)
        self.assertEqual(len(state["doors"]), 1)
        self.assertEqual(state["doors"][0]["dest"], [2, 6])
        self.assertEqual(state["doors"][0]["floor"], 1)
        self.assertAlmostEqual(state["doors"][0]["x"], 130.0, places=4)

        again = tracker.MapTracker(self.cache)   # the cache brings the map back without PCSX2
        self.assertIn(FILE_ID, again.areas)
        self.assertEqual(again.snapshot()["doors"], state["doors"])
        self.assertFalse(again.snapshot()["connected"])

    def test_previous_area_file_is_not_taken(self):
        ram = FakeRam()
        build_game(ram, stage=4, room=0)     # the file still holds stage 2's pieces
        t = tracker.MapTracker(self.cache)
        t.tick(ram)
        t.tick(ram)
        self.assertEqual(t.areas, {})
        self.assertIsNone(t.snapshot()["player"])

    def test_torches_and_disconnect(self):
        ram = FakeRam()
        build_game(ram)
        t = tracker.MapTracker(self.cache)
        t.tick(ram)
        t.tick(ram)
        t.set_ap({"slot": "Leon", "rooms": {"25": [["A", False]]},
                  "torches": [{"name": "T", "stage": 2, "room": 5, "x": 1000.0, "z": 500.0,
                               "checked": True}]})
        snap = t.snapshot()
        self.assertEqual(snap["slot"], "Leon")
        self.assertEqual(snap["torches"][0]["floor"], 0)   # the room's lowest piece
        self.assertAlmostEqual(snap["torches"][0]["x"], 200.0, places=4)
        t.disconnected()
        self.assertFalse(t.snapshot()["connected"])
        self.assertEqual(t.first_keys, [])

    def test_web(self):
        ram = FakeRam()
        build_game(ram)
        t = tracker.MapTracker(self.cache)
        t.tick(ram)
        t.tick(ram)
        url = t.start(port=38490)
        try:
            page = urllib.request.urlopen(url, timeout=5).read()
            self.assertIn(b"three", page)
            state = json.loads(urllib.request.urlopen(url + "api/state", timeout=5).read())
            self.assertEqual(state["area"], FILE_ID)
            maps = json.loads(urllib.request.urlopen(url + "api/maps", timeout=5).read())
            self.assertEqual(maps["areas"][0]["triangles"], 12)
            tris = urllib.request.urlopen(url + f"api/area/{FILE_ID}", timeout=5).read()
            self.assertEqual(len(tris), 12 * 24)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(url + "api/area/7", timeout=5)
        finally:
            t.stop()


if __name__ == "__main__":
    unittest.main()
