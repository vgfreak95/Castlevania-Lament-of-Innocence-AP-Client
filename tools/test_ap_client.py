"""Unit tests for the Lament of Innocence AP client's game protocol (pine.py, game_interface.py),
run against an in-memory fake PCSX2: a fake PINE socket over a bytearray of EE RAM, plus a small
Python model of what src/pickup.c does with it. No emulator or Archipelago install needed.

usage: py -3.13 tools/test_ap_client.py [-v]
"""
import importlib.util
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "apworld", "lament_of_innocence")


def _load(name):
    """Load a client module by path, without importing the world package (needs Archipelago)."""
    spec = importlib.util.spec_from_file_location(f"loi_{name}", os.path.join(PKG, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pine = _load("pine")
gi = _load("game_interface")

RAM_SIZE = 0x02000000


class FakePineSocket:
    """Speaks the PINE wire protocol against `ram`, like PCSX2's PINE server."""

    def __init__(self, ram, game_id="SLUS-20733"):
        self.ram = ram
        self.game_id = game_id
        self.out = bytearray()
        self.requests = 0

    def settimeout(self, t):
        pass

    def close(self):
        pass

    def sendall(self, data):
        size, = struct.unpack_from("<I", data)
        assert size == len(data), "PINE message size field must cover the whole message"
        self.requests += 1
        i, reply = 4, bytearray()
        while i < len(data):
            op = data[i]
            i += 1
            if op in (pine.READ8, pine.READ16, pine.READ32, pine.READ64):
                addr, = struct.unpack_from("<I", data, i)
                i += 4
                n = {pine.READ8: 1, pine.READ16: 2, pine.READ32: 4, pine.READ64: 8}[op]
                assert addr % n == 0, f"unaligned {n}-byte read at {addr:#x}"
                reply += self.ram[addr:addr + n]
            elif op in (pine.WRITE8, pine.WRITE16, pine.WRITE32, pine.WRITE64):
                addr, = struct.unpack_from("<I", data, i)
                i += 4
                n = {pine.WRITE8: 1, pine.WRITE16: 2, pine.WRITE32: 4, pine.WRITE64: 8}[op]
                assert addr % n == 0, f"unaligned {n}-byte write at {addr:#x}"
                self.ram[addr:addr + n] = data[i:i + n]
                i += n
            elif op == pine.ID:
                s = self.game_id.encode() + b"\0"
                reply += struct.pack("<I", len(s)) + s
            elif op == pine.STATUS:
                reply += struct.pack("<I", pine.EMU_RUNNING)
            else:
                raise AssertionError(f"unexpected PINE opcode {op:#x}")
        self.out += struct.pack("<IB", 5 + len(reply), pine.IPC_OK) + reply

    def recv(self, n):
        data, self.out = bytes(self.out[:n]), self.out[n:]
        return data


class FakeGame:
    """The C side (src/pickup.c, msgbox.c) as far as the client can see it."""

    def __init__(self, ram):
        self.ram = ram
        self.applied = 0           # RECV_APPLIED, the counter in the save
        self.given = []            # items given, in order
        self.shown = []            # message box texts shown
        self.boot()

    def u32(self, addr, value=None):
        if value is None:
            return struct.unpack_from("<I", self.ram, addr)[0]
        struct.pack_into("<I", self.ram, addr, value & 0xFFFFFFFF)

    def boot(self):
        self.u32(gi.STATUS, gi.STATUS_MAGIC)
        self.u32(gi.STATUS + 4, gi.PROTOCOL_VERSION)

    def post_event(self, kind, item, location, name=b"Potion"):
        mb = gi.MAILBOX
        seq = self.u32(mb + 4) if self.u32(mb) == gi.MAILBOX_MAGIC else 0
        ev = mb + 16 + (seq % 8) * 256
        struct.pack_into("<Iiii", self.ram, ev, seq, kind, item, location)
        self.ram[ev + 16:ev + 80] = name.ljust(64, b"\0")
        self.u32(mb + 8, 8)
        self.u32(mb + 12, 256)
        self.u32(mb, gi.MAILBOX_MAGIC)
        self.u32(mb + 4, seq + 1)

    def recv_tick(self):
        q = gi.RECVQ
        self.u32(q + 8, self.applied)
        if self.u32(q) != gi.RECV_MAGIC or self.applied >= self.u32(q + 4):
            return False
        e = q + 16 + (self.applied % 16) * 32
        index, item, sender = struct.unpack_from("<Ii24s", self.ram, e)
        if index != self.applied:
            return False
        self.given.append((item, sender.split(b"\0")[0].decode("cp932")))
        self.applied += 1
        self.u32(q + 8, self.applied)
        return True

    def run(self, frames=100):
        for _ in range(frames):
            self.recv_tick()
            head, tail = self.u32(gi.MSGQ), self.u32(gi.MSGQ + 4)
            if head != tail:
                off = gi.MSGQ + 8 + (tail % 8) * 128
                self.shown.append(bytes(self.ram[off:off + 128]).split(b"\0")[0].decode("cp932"))
                self.u32(gi.MSGQ + 4, tail + 1)

    def snapshot(self):
        return bytearray(self.ram), self.applied, list(self.given)

    def restore(self, snap):
        """Load a save state: RAM and the saved counter go back."""
        ram, self.applied, self.given = snap
        self.ram[:] = ram


def make_session(game_id="SLUS-20733"):
    ram = bytearray(RAM_SIZE)
    game = FakeGame(ram)
    sock = FakePineSocket(ram, game_id)
    p = pine.Pine()
    p.sock = sock
    return game, p, gi.LoIInterface(p), sock


class PineTests(unittest.TestCase):
    def test_read_write_unaligned(self):
        _, p, _, _ = make_session()
        p.write(0x1003, bytes(range(1, 20)))
        self.assertEqual(p.read(0x1003, 19), bytes(range(1, 20)))
        self.assertEqual(p.read(0x1000, 3), b"\0\0\0")
        p.write32(0x2000, 0xDEADBEEF)
        self.assertEqual(p.read32(0x2000), 0xDEADBEEF)

    def test_game_id_and_status(self):
        _, p, _, _ = make_session()
        self.assertEqual(p.game_id(), "SLUS-20733")
        self.assertEqual(p.status(), pine.EMU_RUNNING)

    def test_large_read_is_split(self):
        _, p, _, sock = make_session()
        p.read(0x10000, 8 * pine.MAX_BATCH * 2 + 8)
        self.assertEqual(sock.requests, 3)

    def test_not_connected(self):
        with self.assertRaises(pine.PineError):
            pine.Pine().read32(0)

    def test_default_socket_paths(self):
        env = {"XDG_RUNTIME_DIR": "/run/user/1000"}
        self.assertEqual(pine.default_socket_paths(28011, env, "linux"),
                         ["/run/user/1000/pcsx2.sock", "/run/user/1000/app/net.pcsx2.PCSX2/pcsx2.sock",
                          "/tmp/pcsx2.sock"])
        self.assertEqual(pine.default_socket_paths(28012, {}, "linux"), ["/tmp/pcsx2.sock.28012"])
        self.assertEqual(pine.default_socket_paths(28011, {"TMPDIR": "/var/tmp/x"}, "darwin"),
                         ["/var/tmp/x/pcsx2.sock"])
        self.assertEqual(pine.default_socket_paths(28011, env, "win32"), [])

    @unittest.skipUnless(pine.unix_sockets_supported(), "no Unix sockets here")
    def test_unix_socket_connect(self):
        import os
        import socket
        import tempfile
        import threading
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "pcsx2.sock")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(path)
            server.listen(1)
            ram = bytearray(RAM_SIZE)
            fake = FakePineSocket(ram, "SLUS-20733")

            def serve():
                conn, _ = server.accept()
                with conn:
                    while True:
                        head = conn.recv(4)
                        if not head:
                            return
                        size, = struct.unpack("<I", head)
                        body = b""
                        while len(body) < size - 4:
                            body += conn.recv(size - 4 - len(body))
                        fake.sendall(head + body)
                        conn.sendall(bytes(fake.out))
                        fake.out.clear()

            threading.Thread(target=serve, daemon=True).start()
            p = pine.Pine(socket_path=path)
            p.connect()
            self.assertEqual(p.endpoint, f"socket {path}")
            self.assertEqual(p.game_id(), "SLUS-20733")
            p.close()
            server.close()

    def test_explicit_socket_missing(self):
        p = pine.Pine(socket_path="/nonexistent/pcsx2.sock")
        with self.assertRaises(pine.PineError):
            p.connect()


class GameCheckTests(unittest.TestCase):
    def test_ok(self):
        _, _, iface, _ = make_session()
        iface.check_game()

    def test_wrong_game(self):
        _, _, iface, _ = make_session("SLUS-21234")
        with self.assertRaises(gi.GameMismatch):
            iface.check_game()

    def test_patch_missing(self):
        game, _, iface, _ = make_session()
        game.u32(gi.STATUS, 0)
        with self.assertRaises(gi.GameMismatch):
            iface.check_game()

    def test_patch_outdated(self):
        game, _, iface, _ = make_session()
        game.u32(gi.STATUS + 4, 1)
        with self.assertRaises(gi.GameMismatch):
            iface.check_game()


class EventTests(unittest.TestCase):
    def locations(self, events):
        return [e.location for e in events if e.kind == gi.EV_LOCATION]

    def test_empty_mailbox(self):
        _, _, iface, _ = make_session()
        self.assertEqual(iface.poll_events(), [])

    def test_events_in_order(self):
        game, _, iface, _ = make_session()
        self.assertEqual(iface.poll_events(), [])
        game.post_event(gi.EV_LOCATION, 0x2A, 100)
        game.post_event(gi.EV_PICKUP, 0x93, -1)
        game.post_event(gi.EV_LOCATION, 0x2B, 101)
        evs = iface.poll_events()
        self.assertEqual(self.locations(evs), [100, 101])
        self.assertEqual(evs[0].name, "Potion")
        self.assertEqual(iface.poll_events(), [])

    def test_first_poll_reads_whole_ring(self):
        game, _, iface, _ = make_session()
        for loc in range(12):
            game.post_event(gi.EV_LOCATION, 1, loc)
        self.assertEqual(self.locations(iface.poll_events()), list(range(4, 12)))

    def test_overrun_counts_missed(self):
        game, _, iface, _ = make_session()
        game.post_event(gi.EV_LOCATION, 1, 0)
        iface.poll_events()
        for loc in range(1, 12):
            game.post_event(gi.EV_LOCATION, 1, loc)
        self.assertEqual(self.locations(iface.poll_events()), list(range(4, 12)))
        self.assertEqual(iface.missed, 3)

    def test_save_state_going_back(self):
        game, _, iface, _ = make_session()
        game.post_event(gi.EV_LOCATION, 1, 10)
        snap = game.snapshot()
        game.post_event(gi.EV_LOCATION, 1, 11)
        game.post_event(gi.EV_LOCATION, 1, 12)
        self.assertEqual(self.locations(iface.poll_events()), [10, 11, 12])
        game.restore(snap)                         # back to write_seq 1 ...
        game.post_event(gi.EV_LOCATION, 1, 20)     # ... and a new pickup before the next poll
        self.assertIn(20, self.locations(iface.poll_events()))

    def test_save_state_same_count_other_history(self):
        game, _, iface, _ = make_session()
        game.post_event(gi.EV_LOCATION, 1, 10)
        snap = game.snapshot()
        game.post_event(gi.EV_LOCATION, 1, 11)
        iface.poll_events()
        game.restore(snap)
        game.post_event(gi.EV_LOCATION, 1, 30)     # same write_seq as before the load
        self.assertIn(30, self.locations(iface.poll_events()))


class ItemTests(unittest.TestCase):
    ITEMS = [(0x2A, "Alice"), (0x5D, "Bob"), (0x7F, "ボブ"), (0x91, "Carol")]

    def test_items_given_once_in_order(self):
        game, _, iface, _ = make_session()
        for _ in range(5):
            iface.sync_items(self.ITEMS)
            game.run(3)
        self.assertEqual(game.given, self.ITEMS)

    def test_items_arrive_later(self):
        game, _, iface, _ = make_session()
        iface.sync_items(self.ITEMS[:1])
        game.run()
        iface.sync_items(self.ITEMS)
        game.run()
        iface.sync_items(self.ITEMS)
        game.run()
        self.assertEqual(game.given, self.ITEMS)

    def test_more_than_ring(self):
        game, _, iface, _ = make_session()
        items = [(0x2A + (i % 5), f"P{i}") for i in range(40)]
        for _ in range(10):
            iface.sync_items(items)
            game.run(5)
        self.assertEqual(game.given, items)

    def test_reload_older_save_resends(self):
        game, _, iface, _ = make_session()
        iface.sync_items(self.ITEMS[:2])
        game.run()
        snap = game.snapshot()            # save with 2 items applied
        iface.sync_items(self.ITEMS)
        game.run()
        self.assertEqual(game.applied, 4)
        game.restore(snap)                # load it: the client must resend items 2 and 3
        for _ in range(3):
            iface.sync_items(self.ITEMS)
            game.run()
        self.assertEqual(game.given, self.ITEMS)

    def test_save_ahead_of_server(self):
        game, _, iface, _ = make_session()
        game.applied = 3                  # e.g. items still on their way after a reconnect
        iface.sync_items(self.ITEMS[:1])
        game.run()
        self.assertEqual(game.given, [])
        iface.sync_items(self.ITEMS)
        game.run()
        self.assertEqual(game.given, [self.ITEMS[3]])

    def test_sender_truncated_cp932(self):
        game, _, iface, _ = make_session()
        long_name = "あ" * 20                # 40 bytes in cp932
        iface.sync_items([(0x2A, long_name)])
        game.run()
        sender = game.given[0][1]
        self.assertTrue(long_name.startswith(sender))
        self.assertLessEqual(len(sender.encode("cp932")), gi.SENDER_BYTES)

    def test_entries_before_count(self):
        """The game may run between any two PINE writes: count must come last."""
        game, p, iface, sock = make_session()
        original = sock.sendall
        def sendall(data):
            original(data)
            game.recv_tick()              # a game frame after every PINE message
        sock.sendall = sendall
        iface.sync_items(self.ITEMS)
        game.run()
        self.assertEqual(game.given, self.ITEMS)


class StatusAndMessageTests(unittest.TestCase):
    def test_goal_bits(self):
        game, _, iface, _ = make_session()
        self.assertEqual(iface.status().goal, 0)
        game.u32(gi.STATUS + 8, gi.GOAL_WALTER)
        struct.pack_into("<2H", game.ram, gi.CUR_STAGE, 5, 0x29)
        st = iface.status()
        self.assertEqual(st.goal, gi.GOAL_WALTER)
        self.assertEqual((st.stage, st.room), (5, 0x29))

    def test_deathlink_counters(self):
        game, _, iface, _ = make_session()
        st = iface.status()
        self.assertEqual((st.deaths, st.kill_req), (0, 0))
        game.u32(gi.STATUS + 24, 2)                    # the game counted two deaths
        self.assertEqual(iface.status().deaths, 2)
        iface.request_kill()
        iface.request_kill()
        self.assertEqual(game.u32(gi.STATUS_KILL_REQ), 2)
        self.assertEqual(iface.status().kill_req, 2)

    def test_area_locks(self):
        game, _, iface, _ = make_session()
        self.assertEqual(gi.STATUS_AREA_LOCKS, gi.STATUS + 32)   # ap.h: after kill_req
        iface.set_area_locks(0x1F)
        self.assertEqual(game.u32(gi.STATUS_AREA_LOCKS), 0x1F)
        game.u32(gi.STATUS_AREA_LOCKS, 0)                        # console reset clears it
        iface.set_area_locks(0x1F)
        self.assertEqual(game.u32(gi.STATUS_AREA_LOCKS), 0x1F)
        self.assertEqual(iface.status().kill_req, 0)             # neighbours untouched

    def test_skill_vanilla(self):
        game, _, iface, _ = make_session()
        self.assertEqual(gi.STATUS_SKILL_VANILLA, gi.STATUS + 36)  # ap.h: after area_locks
        iface.set_skill_vanilla(0x5000)
        self.assertEqual(game.u32(gi.STATUS_SKILL_VANILLA), 0x5000)
        game.u32(gi.STATUS_SKILL_VANILLA, 0)                       # console reset clears it
        iface.set_skill_vanilla(0x5000)
        self.assertEqual(game.u32(gi.STATUS_SKILL_VANILLA), 0x5000)
        self.assertEqual(game.u32(gi.STATUS_AREA_LOCKS), 0)        # neighbour untouched

    def test_qol(self):
        game, _, iface, _ = make_session()
        self.assertEqual(gi.STATUS_QOL, gi.STATUS + 40)             # ap.h: after skill_vanilla
        self.assertEqual(gi.STATUS_STRUCT.size, 44)
        iface.set_qol(gi.qol_wolfs_foot(50))
        self.assertEqual(game.u32(gi.STATUS_QOL), 0x3201)          # bit 0 + 50% in bits 8-15
        game.u32(gi.STATUS_QOL, 0)                                 # console reset clears it
        iface.set_qol(gi.qol_wolfs_foot(50))
        self.assertEqual(game.u32(gi.STATUS_QOL), 0x3201)
        self.assertEqual(gi.qol_wolfs_foot(0), 0x0001)             # no drain
        self.assertEqual(gi.qol_wolfs_foot(100), 0)                # normal: vanilla
        self.assertEqual(gi.qol_wolfs_foot(250), 0)                # clamped
        self.assertEqual(game.u32(gi.STATUS_SKILL_VANILLA), 0)     # neighbour untouched

    def test_progressive(self):
        brooch, plate = 768, 769
        got = gi.resolve_progressive([plate, 0x2A, brooch, plate, brooch, plate, plate, plate])
        self.assertEqual(got, [0x06, 0x2A, 0x17, 0x07, 0x18, 0x08, 0x09, 0x09])  # extra = last tier
        self.assertEqual(gi.resolve_progressive([0x2A, 0xAA]), [0x2A, 0xAA])     # others untouched

    def test_heartbeat_changes(self):
        game, _, iface, _ = make_session()
        iface.heartbeat()
        a = game.u32(gi.STATUS_CLIENT_TICKS)
        iface.heartbeat()
        self.assertNotEqual(a, game.u32(gi.STATUS_CLIENT_TICKS))
        self.assertNotEqual(a, 0)

    def test_messages(self):
        game, _, iface, _ = make_session()
        for i in range(10):
            ok = iface.post_message(f"^C80ff8080Sent^c\nItem {i}\nto Bob")
            self.assertEqual(ok, i < 8)
        game.run(20)
        self.assertEqual(len(game.shown), 8)
        self.assertEqual(game.shown[0], "^C80ff8080Sent^c\nItem 0\nto Bob")
        self.assertTrue(iface.post_message("x" * 300))
        game.run(1)
        self.assertEqual(len(game.shown[-1]), gi.MSGQ_TEXT - 1)


class LocScanTests(unittest.TestCase):
    """tools/loc_scan.py against a fake ISO with two rooms holding the same item and flag at
    almost the same position (as several max-up rooms do on the real disc)."""

    def test_match(self):
        import tempfile
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import loc_scan

        def record(item, flag, pos):
            rec = bytearray(0x80)
            struct.pack_into("<HH", rec, 0, 1, loc_scan.CLASS_PLACED_ITEM)
            struct.pack_into("<iI", rec, 0x10, item, ((flag + 1) << 16) | 0)
            struct.pack_into("<3f", rec, 0x60, *pos)
            return rec

        iso = bytearray(0x1000)
        iso[0x100:0x180] = record(0x90, 0, (2001.74, -500.0, 3699.1))
        iso[0x400:0x480] = record(0x90, 0, (2000.54, -500.0, 3699.3))
        iso[0x800:0x880] = record(0x45, -1, (1.0, 2.0, 3.0))
        with tempfile.TemporaryDirectory() as tmp:
            iso_path = os.path.join(tmp, "fake.iso")
            with open(iso_path, "wb") as f:
                f.write(iso)
            log_path = os.path.join(tmp, "emulog.txt")
            with open(log_path, "w") as f:
                for key, off in ((7, 0x100), (9, 0x400)):
                    bits = struct.unpack_from("<3I", iso, off + 0x60)
                    pos = struct.unpack_from("<3f", iso, off + 0x60)
                    f.write(f"junk [locscan] stage 1 room {key} key {key} flag 0 item 90 pos "
                            f"{int(pos[0])} {int(pos[1])} {int(pos[2])} bits {bits[0]:08X} "
                            f"{bits[1]:08X} {bits[2]:08X} game_key {key * 64}\n")
            locs = [
                {"name": "A", "ap_id": 1, "kind": "pickup", "vanilla_item": 0x90, "iso_offset": 0x110},
                {"name": "B", "ap_id": 2, "kind": "pickup", "vanilla_item": 0x90, "iso_offset": 0x410},
                {"name": "C", "ap_id": 3, "kind": "pickup", "vanilla_item": 0x45, "iso_offset": 0x810},
                {"name": "Golem", "ap_id": 4, "kind": "boss", "vanilla_item": 0x7F,
                 "iso_offset": 0x44F590},
            ]
            keys, problems = loc_scan.match(locs, iso_path, loc_scan.parse_logs([log_path]))
        self.assertEqual(keys, {1: 7 * 64, 2: 9 * 64, 4: 0x8000})
        self.assertEqual(len(problems), 1)       # C has no collected flag


class DataTests(unittest.TestCase):
    def test_key_map_and_boss_keys(self):
        recs = [{"ap_id": 1, "game_key": 5}, {"ap_id": 2, "game_key": None}]
        self.assertEqual(gi.build_key_map(recs), {5: 1})
        self.assertEqual(gi.boss_game_key(0x44F590), 0x8000)
        self.assertEqual(gi.boss_game_key(0x44F5B8), 0x800A)

    def test_torch_data(self):
        """data/torches.json: unique ids, keys and torch identities; no weapon torches."""
        import json
        with open(os.path.join(PKG, "data", "torches.json"), encoding="utf-8") as f:
            torches = json.load(f)
        self.assertGreater(len(torches), 1000)
        for field in ("ap_id", "game_key", "name"):
            self.assertEqual(len({t[field] for t in torches}), len(torches), field)
        self.assertEqual(len({(t["room_key"], t["x_bits"], t["z_bits"]) for t in torches}),
                         len(torches))
        for t in torches:
            self.assertEqual(t["game_key"] - 0x10000, t["ap_id"] - 207350000)
            self.assertFalse(0xAA <= t["vanilla_item"] <= 0xAF, t["name"])
            self.assertLess(t["room_key"], 0x10000)


def torch_spots(n, checked=()):
    return [gi.TorchSpot(room_key=10 + i // 3, x_bits=0x44000000 + i, z_bits=0x45000000 + i,
                         game_key=0x10000 + i, checked=i in checked)
            for i in range(n)]


class TorchTableModel:
    """What src/torches.c sees of the table."""

    def __init__(self, ram):
        self.ram = ram

    def header(self):
        return gi.TORCH_HEADER.unpack_from(self.ram, gi.TORCH_TABLE)

    def entries(self):
        magic, count, _, _ = self.header()
        if magic != gi.TORCH_TABLE_MAGIC:
            return None
        base = gi.TORCH_TABLE + gi.TORCH_HEADER.size
        return [gi.TORCH_ENTRY.unpack_from(self.ram, base + i * gi.TORCH_ENTRY.size)
                for i in range(count)]

    def break_torch(self, i):
        """The red torch breaks: the game sets TF_CHECKED and bumps checked_seq (torch_drop_hook)."""
        addr = gi.TORCH_TABLE + gi.TORCH_HEADER.size + i * gi.TORCH_ENTRY.size + gi.TORCH_FLAGS_OFFSET
        struct.pack_into("<I", self.ram, addr, gi.TF_CHECKED)
        seq_addr = gi.TORCH_TABLE + 8
        struct.pack_into("<I", self.ram, seq_addr, struct.unpack_from("<I", self.ram, seq_addr)[0] + 1)


class TorchTests(unittest.TestCase):
    def setUp(self):
        self.game, _, self.iface, self.sock = make_session()
        self.table = TorchTableModel(self.game.ram)

    def test_layout_matches_c(self):
        self.assertEqual(gi.TORCH_ENTRY.size, 20)          # torches.h TorchEntry
        self.assertEqual(gi.TORCH_TABLE + gi.TORCH_HEADER.size + gi.TORCH_TABLE_MAX * 20, 0xC7810)
        # torches.h TorchChecks (16-byte header + 8 x 20) sits between the table and TORCH_SCAN
        self.assertTrue(0xC7810 <= 0xC7900 and 0xC7900 + 16 + 8 * 20 <= 0xC8000)

    def test_writes_table(self):
        spots = torch_spots(5, checked={2})
        self.assertEqual(self.iface.sync_torches(spots), [])
        rows = self.table.entries()
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0], (10, 0, 0x44000000, 0x45000000, 0x10000, 0))
        self.assertEqual(rows[2][5], gi.TF_CHECKED)

    def test_no_spots_clears_table(self):
        self.iface.sync_torches(torch_spots(3))
        self.iface.sync_torches([])
        self.assertIsNone(self.table.entries())

    def test_new_check_sets_flag_without_rewrite(self):
        self.iface.sync_torches(torch_spots(4))
        before = self.sock.requests
        self.iface.sync_torches(torch_spots(4, checked={1}))
        self.assertEqual(self.table.entries()[1][5], gi.TF_CHECKED)
        self.assertLessEqual(self.sock.requests - before, 2)   # header read + one flag write

    def test_broken_torch_is_reported_once(self):
        """A torch the game checked is returned on the next sync (checked_seq moved), once."""
        self.iface.sync_torches(torch_spots(4))
        self.table.break_torch(3)
        self.assertEqual(self.iface.sync_torches(torch_spots(4)), [0x10003])
        self.assertEqual(self.iface.sync_torches(torch_spots(4)), [])
        for _ in range(gi.TORCH_VERIFY_POLLS + 1):        # a full re-read still sees the flag:
            found = self.iface.sync_torches(torch_spots(4))
            self.assertIn(found, ([], [0x10003]))         # reported until the server knows
        self.assertEqual(self.table.entries()[3][5], gi.TF_CHECKED)   # not undone
        self.table.break_torch(0)
        self.assertEqual(self.iface.sync_torches(torch_spots(4, checked={3})), [0x10000])

    def test_torch_known_checked_not_reported(self):
        self.iface.sync_torches(torch_spots(4, checked={1}))
        self.table.break_torch(1)                          # e.g. broken again after a reload
        self.assertEqual(self.iface.sync_torches(torch_spots(4, checked={1})), [])

    def test_other_tables_flag_is_not_a_check(self):
        """A save state with another slot's table: its flags don't count, the table is fixed."""
        self.iface.sync_torches(torch_spots(4))
        other = gi.TorchSpot(99, 1, 2, 0x10002, checked=True).entry()
        base = gi.TORCH_TABLE + gi.TORCH_HEADER.size
        self.game.ram[base + 2 * 20:base + 3 * 20] = other
        struct.pack_into("<I", self.game.ram, gi.TORCH_TABLE + 8, 5)   # its checked_seq
        self.assertEqual(self.iface.sync_torches(torch_spots(4)), [])
        self.assertEqual(self.table.entries()[2], (10, 0, 0x44000002, 0x45000002, 0x10002, 0))

    def test_console_reset_rewrites(self):
        self.iface.sync_torches(torch_spots(4, checked={0}))
        self.game.ram[gi.TORCH_TABLE:gi.TORCH_TABLE + 0x200] = bytes(0x200)
        self.iface.sync_torches(torch_spots(4, checked={0}))
        rows = self.table.entries()
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0][5], gi.TF_CHECKED)

    def test_save_state_with_older_table_is_fixed(self):
        """A save state from before a check (same layout, flag clear) gets the flag back."""
        self.iface.sync_torches(torch_spots(4))
        snap = self.game.snapshot()
        self.iface.sync_torches(torch_spots(4, checked={2}))
        self.game.restore(snap)                  # the table loses torch 2's flag
        for _ in range(gi.TORCH_VERIFY_POLLS):
            self.iface.sync_torches(torch_spots(4, checked={2}))
        self.assertEqual(self.table.entries()[2][5], gi.TF_CHECKED)

    def test_layout_change_rewrites(self):
        self.iface.sync_torches(torch_spots(4))
        spots = torch_spots(4)
        spots[1] = gi.TorchSpot(spots[1].room_key, spots[1].x_bits, spots[1].z_bits, 0x10055)
        self.iface.sync_torches(spots)
        self.assertEqual(self.table.entries()[1][4], 0x10055)


def shop_slots(n, checked=(), price=500):
    return [gi.ShopEntry(gi.shop_game_key(i), price + i, i % 3, f"Item {i}", f"Item {i}\nfor you",
                         checked=i in checked)
            for i in range(n)]


class ShopTableModel:
    """What src/apshop.c and pickup.c see of the shop table."""

    def __init__(self, ram):
        self.ram = ram

    def header(self):
        return gi.SHOP_HEADER.unpack_from(self.ram, gi.SHOP_TABLE)

    def slots(self):
        magic, count = self.header()[:2]
        if magic != gi.SHOP_TABLE_MAGIC:
            return None
        base = gi.SHOP_TABLE + gi.SHOP_HEADER.size
        return [gi.SHOP_SLOT.unpack_from(self.ram, base + i * gi.SHOP_SLOT.size)
                for i in range(count)]

    def buy(self, i):
        """shop_buy_hook: checked and report set, checked_seq bumped."""
        addr = gi.SHOP_TABLE + gi.SHOP_HEADER.size + i * gi.SHOP_SLOT.size
        struct.pack_into("<2I", self.ram, addr + gi.SHOP_CHECKED_OFFSET, 1, 1)
        seq_addr = gi.SHOP_TABLE + 12
        struct.pack_into("<I", self.ram, seq_addr, struct.unpack_from("<I", self.ram, seq_addr)[0] + 1)


class ShopTests(unittest.TestCase):
    def setUp(self):
        self.game, _, self.iface, self.sock = make_session()
        self.table = ShopTableModel(self.game.ram)

    def test_layout_matches_c(self):
        self.assertEqual(gi.SHOP_SLOT.size, 224)            # apshop.h ShopSlot
        self.assertEqual(gi.SHOP_HEADER.size, 32)
        end = gi.SHOP_TABLE + gi.SHOP_HEADER.size + gi.SHOP_SLOTS_MAX * gi.SHOP_SLOT.size
        self.assertEqual(end, 0xB7820)
        self.assertLessEqual(end, 0xB7F00)                   # the debug menu's map mailbox
        self.assertEqual(gi.SHOP_VANILLA_ALL, 0x7FFF)
        self.assertEqual(len(gi.SHOP_VANILLA_ITEMS), 15)
        # game_keys clear of pickups (room_key * 64 + flag), boss rewards and torches
        self.assertGreater(gi.SHOP_KEY_BASE, 0x10000 + gi.TORCH_TABLE_MAX)
        self.assertLess(gi.SHOP_EVENT_ID, gi.SHOP_KEY_BASE)

    def test_writes_table(self):
        self.assertEqual(self.iface.sync_shop(True, 0x1234, shop_slots(3, checked={1})), [])
        magic, count, vanilla = self.table.header()[:3]
        self.assertEqual((magic, count, vanilla), (gi.SHOP_TABLE_MAGIC, 3, 0x1234))
        rows = self.table.slots()
        self.assertEqual(rows[0][:5], (0x20000, 500, 0, 0, 0))
        self.assertEqual(rows[1][3], 1)
        self.assertEqual(rows[2][8].split(b"\0")[0], b"Item 2")
        self.assertEqual(rows[2][9].split(b"\0")[0], b"Item 2\nfor you")

    def test_prices_are_clamped(self):
        slots = [gi.ShopEntry(0x20000, 0), gi.ShopEntry(0x20001, 99999)]
        self.iface.sync_shop(True, 0, slots)
        self.assertEqual([r[1] for r in self.table.slots()], [gi.SHOP_PRICE_MIN, gi.SHOP_PRICE_MAX])

    def test_disabled_clears_table(self):
        self.iface.sync_shop(True, 0, shop_slots(2))
        self.iface.sync_shop(False, 0, [])
        self.assertIsNone(self.table.slots())

    def test_no_slots_still_sets_vanilla(self):
        self.iface.sync_shop(True, 0x0003, [])
        self.assertEqual(self.table.header()[:3], (gi.SHOP_TABLE_MAGIC, 0, 0x0003))

    def test_new_check_sets_flag_without_rewrite(self):
        self.iface.sync_shop(True, 0, shop_slots(4))
        before = self.sock.requests
        self.iface.sync_shop(True, 0, shop_slots(4, checked={2}))
        self.assertEqual(self.table.slots()[2][3], 1)
        self.assertLessEqual(self.sock.requests - before, 2)   # header read + one flag write

    def test_bought_slot_is_reported(self):
        self.iface.sync_shop(True, 0, shop_slots(4))
        self.table.buy(1)
        self.assertEqual(self.iface.sync_shop(True, 0, shop_slots(4)), [0x20001])
        self.assertEqual(self.iface.sync_shop(True, 0, shop_slots(4)), [])
        self.assertEqual(self.iface.sync_shop(True, 0, shop_slots(4, checked={1})), [])
        self.assertEqual(self.table.slots()[1][3], 1)

    def test_purchase_survives_layout_change(self):
        """Bought, then the layout changes before a poll saw it (e.g. scout names arrive): the
        purchase is still returned, and kept checked in the new table."""
        old = [gi.ShopEntry(0x20000 + i, 100) for i in range(3)]
        self.iface.sync_shop(True, 0, old)
        self.table.buy(2)
        new = [gi.ShopEntry(0x20000 + i, 100, name=f"Real {i}") for i in range(3)]
        self.assertEqual(self.iface.sync_shop(True, 0, new), [])        # texts differ: not ours
        old_again = [gi.ShopEntry(0x20000 + i, 100) for i in range(3)]
        self.iface.sync_shop(True, 0, old_again)
        self.table.buy(0)
        changed_vanilla = old_again
        self.assertEqual(self.iface.sync_shop(True, 0x1, changed_vanilla), [0x20000])
        self.assertEqual(self.table.slots()[0][3], 1)
        self.assertEqual(self.table.header()[2], 0x1)

    def test_other_tables_flag_is_not_a_check(self):
        """A save state with another seed's shop (same game_keys, other texts): no checks."""
        self.iface.sync_shop(True, 0, shop_slots(3))
        other = gi.ShopEntry(0x20001, 777, name="Other seed", checked=True).entry()
        base = gi.SHOP_TABLE + gi.SHOP_HEADER.size
        self.game.ram[base + gi.SHOP_SLOT.size:base + 2 * gi.SHOP_SLOT.size] = other
        struct.pack_into("<I", self.game.ram, gi.SHOP_TABLE + 12, 9)
        self.assertEqual(self.iface.sync_shop(True, 0, shop_slots(3)), [])
        self.assertEqual(self.table.slots()[1][:4], (0x20001, 501, 1, 0))

    def test_console_reset_rewrites(self):
        self.iface.sync_shop(True, 0x7FFF, shop_slots(3, checked={0}))
        self.game.ram[gi.SHOP_TABLE:gi.SHOP_TABLE + 0x400] = bytes(0x400)
        self.iface.sync_shop(True, 0x7FFF, shop_slots(3, checked={0}))
        rows = self.table.slots()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][3], 1)

    def test_save_state_with_older_table_is_fixed(self):
        self.iface.sync_shop(True, 0, shop_slots(3))
        snap = self.game.snapshot()
        self.iface.sync_shop(True, 0, shop_slots(3, checked={2}))
        self.game.restore(snap)                   # the table loses slot 2's flag
        for _ in range(gi.SHOP_VERIFY_POLLS):
            self.iface.sync_shop(True, 0, shop_slots(3, checked={2}))
        self.assertEqual(self.table.slots()[2][3], 1)

    def test_event_for_shop_key_is_a_location(self):
        self.iface.sync_shop(True, 0, shop_slots(2))
        self.game.post_event(gi.EV_LOCATION, gi.SHOP_EVENT_ID + 1, gi.shop_game_key(1), b"Item 1")
        ev = self.iface.poll_events()[-1]
        self.assertEqual((ev.kind, ev.location, ev.item), (gi.EV_LOCATION, 0x20001, 0x101))

    def test_texts(self):
        name, desc = gi.shop_texts("Hookshot", "Alice", False, gi.AP_FLAG_PROGRESSION)
        self.assertEqual(name, "Alice's Hookshot")
        self.assertEqual(desc, "Hookshot\nfor Alice (progression)")
        name, _ = gi.shop_texts("Progressive Sword Upgrade", "Bob", False, 0)
        self.assertLessEqual(len(name), gi.SHOP_NAME_CHARS)
        self.assertTrue(name.startswith("Progressive Sw") and name.endswith(".."))
        name, desc = gi.shop_texts("Whip of Flames", "Leon", True, gi.AP_FLAG_USEFUL)
        self.assertEqual(name, "Whip of Flames")
        self.assertTrue(desc.endswith("for you (useful)"))
        name, _ = gi.shop_texts("^C80ff0000Red^c", "x", True, 0)
        self.assertNotIn("^", name)
        for line in gi.shop_texts("A" * 100, "B" * 100, False, 0)[1].split("\n"):
            self.assertLessEqual(len(line), gi.SHOP_DESC_CHARS)

    def test_looks(self):
        self.assertEqual(gi.shop_look(gi.AP_FLAG_PROGRESSION | gi.AP_FLAG_USEFUL),
                         gi.SHOP_LOOK_PROGRESSION)
        self.assertEqual(gi.shop_look(gi.AP_FLAG_USEFUL), gi.SHOP_LOOK_USEFUL)
        self.assertEqual(gi.shop_look(gi.AP_FLAG_TRAP), gi.SHOP_LOOK_FILLER)
        self.assertEqual(gi.shop_look(0), gi.SHOP_LOOK_FILLER)

    def test_long_text_is_cut_to_the_c_buffers(self):
        e = gi.ShopEntry(0x20000, 10, name="N" * 100, desc="D" * 500).entry()
        _, _, _, _, _, _, _, _, name, desc = gi.SHOP_SLOT.unpack(e)
        self.assertEqual(name[-1], 0)              # NUL-terminated in 32 bytes
        self.assertEqual(desc[-1], 0)


if __name__ == "__main__":
    unittest.main()
