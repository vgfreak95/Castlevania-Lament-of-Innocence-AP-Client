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


if __name__ == "__main__":
    unittest.main()
