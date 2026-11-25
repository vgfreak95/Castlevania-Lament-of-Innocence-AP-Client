"""Game side of the Lament of Innocence AP client: the RAM protocol of the "Archipelago Pickups"
patch (src/pickup.c, src/msgbox.h, src/ap.h), spoken over PINE.

- Event mailbox @ 0xFC000: the game reports location checks (EV_LOCATION, location = game_key).
- Status block @ 0xFCF00: protocol version, goal bits, location-scan flag, client heartbeat.
- Message queue @ 0xFD000: the client may post popups ("Sent X to Y").
- Receive ring @ 0xFE000: the client writes the server's items; the game gives them in order and
  keeps how many it has given (`applied`) in the save.
- Torch table @ 0xC0000 (src/torches.h, Torch Sanity): the client lists the slot's torch
  locations (room key, position, game_key, checked flag); the "Archipelago Torches" patch makes
  the unchecked ones burn red, and breaking one sets its checked flag and reports the location
  through the event mailbox (it drops nothing).

No Archipelago imports, so tools/test_ap_client.py can run it against an in-memory fake.
Every address and layout here must match the C side.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Sequence, Tuple

GAME_ID = "SLUS-20733"

# ---- event mailbox (pickup.c) ----
MAILBOX = 0x000FC000
MAILBOX_MAGIC = 0x50554B50          # "PKUP"
MAILBOX_HEADER = struct.Struct("<4I")  # magic, write_seq, slot_count, slot_size
MAILBOX_SLOTS = 8
EVENT_SIZE = 256
EVENT_HEAD = struct.Struct("<Iiii")  # seq, kind, id, location; then name[64], desc[176]
EV_PICKUP, EV_LOCATION = 0, 1

# ---- status block (ap.h) ----
STATUS = 0x000FCF00
# magic, version, goal, scan, client_ticks, hud_off, deaths (game), kill_req (client),
# area_locks (client), skill_vanilla (client), qol (client)
STATUS_STRUCT = struct.Struct("<11I")
STATUS_MAGIC = 0x54535041           # "APST"
PROTOCOL_VERSION = 7                # 7: torch table
STATUS_CLIENT_TICKS = STATUS + 16
STATUS_KILL_REQ = STATUS + 28
STATUS_AREA_LOCKS = STATUS + 32     # bit i = area i (items.py AREA_KEYS) needs its key
STATUS_SKILL_VANILLA = STATUS + 36  # skills (src/skills.h bits) still learned the normal way
STATUS_QOL = STATUS + 40            # quality-of-life options (src/qol.h bits)
QOL_WOLFS_FOOT = 0x1

# Progressive items (items.py PROGRESSIVE), by their items.json game_id: the nth one received
# becomes the nth tier's game item ID (any beyond the last tier repeat the last).
PROGRESSIVE_TIERS: Dict[int, List[int]] = {
    768: [0x17, 0x18],              # Progressive Brooch: Heart Brooch, Mobius's Brooch
    769: [0x06, 0x07, 0x08, 0x09],  # Progressive Plate: Earth, Meteor, Moonlight, Solar Plate
}


def resolve_progressive(game_ids: Sequence[int]) -> List[int]:
    """Game item IDs as received (server order), with each progressive item replaced by its
    tier. Depends only on the order, so every resend of the list gives the same items."""
    seen: Dict[int, int] = {}
    out = []
    for gid in game_ids:
        tiers = PROGRESSIVE_TIERS.get(gid)
        if tiers is None:
            out.append(gid)
            continue
        n = seen.get(gid, 0)
        seen[gid] = n + 1
        out.append(tiers[min(n, len(tiers) - 1)])
    return out
GOAL_WALTER, GOAL_DEATH = 0x1, 0x2

# ---- message queue (msgbox.h) ----
MSGQ = 0x000FD000
MSGQ_SLOTS = 8
MSGQ_TEXT = 128
MSGQ_HEADER = struct.Struct("<2I")   # head, tail

# ---- receive ring (pickup.c) ----
RECVQ = 0x000FE000
RECV_MAGIC = 0x56434552              # "RECV"
RECV_SLOTS = 16
RECV_HEADER = struct.Struct("<4I")   # magic, count, applied, reserved
RECV_ENTRY = struct.Struct("<Ii24s")  # index, item, sender (cp932, NUL-terminated)
SENDER_BYTES = 23

# ---- torch table (torches.h) ----
TORCH_TABLE = 0x000C0000
TORCH_TABLE_MAGIC = 0x48435254       # "TRCH"
TORCH_TABLE_MAX = 1536
TORCH_HEADER = struct.Struct("<4I")  # magic, count, checked_seq, reserved
TORCH_ENTRY = struct.Struct("<HHIIII")  # room_key, reserved (0), x_bits, z_bits, game_key, flags
TORCH_FLAGS_OFFSET = 16              # of flags in an entry
TF_CHECKED = 0x1
TORCH_VERIFY_POLLS = 30              # re-read the whole table this often (save states, resets)

# ---- game state ----
CUR_STAGE = 0x00738E94               # u16 stage, u16 room
BOSS_KEY_BASE = 0x8000               # boss reward game_key = BOSS_KEY_BASE + reward index


class Memory(Protocol):
    def read(self, addr: int, length: int) -> bytes: ...
    def write(self, addr: int, data: bytes) -> None: ...
    def write32(self, addr: int, value: int) -> None: ...
    def game_id(self) -> str: ...


class GameMismatch(Exception):
    """PCSX2 runs something else, or the pickup patch is missing or outdated."""


@dataclass
class GameEvent:
    seq: int
    kind: int
    item: int
    location: int
    name: str


@dataclass(frozen=True)
class TorchSpot:
    """One torch location of the slot, as the game's torch table holds it."""
    room_key: int
    x_bits: int
    z_bits: int
    game_key: int
    checked: bool = False

    def entry(self) -> bytes:
        return TORCH_ENTRY.pack(self.room_key, 0, self.x_bits, self.z_bits, self.game_key,
                                TF_CHECKED if self.checked else 0)

    def unchecked(self) -> "TorchSpot":
        return TorchSpot(self.room_key, self.x_bits, self.z_bits, self.game_key)


@dataclass
class GameStatus:
    goal: int
    scan: bool
    stage: int
    room: int
    deaths: int = 0      # Leon's deaths since boot, without the ones DeathLink caused
    kill_req: int = 0    # DeathLink kills requested by the client so far


def game_text(raw: bytes) -> str:
    """C string from the game: Shift-JIS (cp932); the game's ^ colour codes are left in."""
    return raw.split(b"\0", 1)[0].decode("cp932", errors="replace")


def encode_text(text: str, max_bytes: int) -> bytes:
    """`text` as cp932 bytes, at most `max_bytes`, never cutting a double-byte character."""
    out = bytearray()
    for ch in text:
        b = ch.encode("cp932", errors="replace")
        if len(out) + len(b) > max_bytes:
            break
        out += b
    return bytes(out)


class LoIInterface:
    """One PCSX2 session. Call check_game() after connecting, then poll regularly."""

    def __init__(self, mem: Memory):
        self.mem = mem
        self.last_seq: Optional[int] = None
        # (seq, kind, location) of the newest event read; a save-state load can put a different
        # event under the same sequence number
        self.last_event: Optional[Tuple[int, int, int]] = None
        self.missed = 0
        self.ticks = 0
        # torch table: the layout last written (spots without their checked flag), the checked
        # flags as far as we know them, polls until the next full re-read and the game's
        # checked_seq at the last one
        self.torch_layout: Optional[Tuple[TorchSpot, ...]] = None
        self.torch_checked: List[bool] = []
        self.torch_verify = 0
        self.torch_seq = 0

    # ---- connection check ----
    def check_game(self) -> None:
        gid = self.mem.game_id().strip().upper().replace("_", "-").replace(".", "")
        if gid and gid != GAME_ID:
            raise GameMismatch(f"PCSX2 is running {gid}, not Lament of Innocence ({GAME_ID})")
        magic, version = struct.unpack("<2I", self.mem.read(STATUS, 8))
        if magic != STATUS_MAGIC:
            raise GameMismatch("the Archipelago Pickups patch isn't running (no status block at "
                               f"{STATUS:#x}); install the pnach and enable its cheats, then boot "
                               "the game past the title screen")
        if version != PROTOCOL_VERSION:
            raise GameMismatch(f"the pickup patch speaks protocol {version}, this client "
                               f"{PROTOCOL_VERSION}; rebuild/reinstall the pnach")

    # ---- status ----
    def status(self) -> GameStatus:
        raw = self.mem.read(STATUS, STATUS_STRUCT.size)
        magic, _version, goal, scan, _ticks, _hud, deaths, kill_req, _locks, _skills, _qol = \
            STATUS_STRUCT.unpack_from(raw)
        stage, room = struct.unpack("<2H", self.mem.read(CUR_STAGE, 4))
        if magic != STATUS_MAGIC:
            goal, scan, deaths, kill_req = 0, 0, 0, 0
        return GameStatus(goal=goal, scan=scan == 0x4E414353, stage=stage, room=room,
                          deaths=deaths, kill_req=kill_req)

    # ---- DeathLink ----
    def request_kill(self) -> None:
        """Kill Leon for a received DeathLink: the game acts once per change of kill_req, as soon
        as gameplay allows it."""
        kill_req, = struct.unpack("<I", self.mem.read(STATUS_KILL_REQ, 4))
        self.mem.write32(STATUS_KILL_REQ, (kill_req + 1) & 0xFFFFFFFF)

    # ---- Area Keys ----
    def set_area_locks(self, mask: int) -> None:
        """Which hub areas need their key (bit i = items.py AREA_KEYS[i]). Written every poll:
        the game clears it on a console reset."""
        current, = struct.unpack("<I", self.mem.read(STATUS_AREA_LOCKS, 4))
        if current != mask:
            self.mem.write32(STATUS_AREA_LOCKS, mask)

    # ---- Skills ----
    def set_skill_vanilla(self, mask: int) -> None:
        """Which whip skills the game may still learn from kills (src/skills.h bits; the rest only
        come as items). Written every poll: the game clears it on a console reset."""
        current, = struct.unpack("<I", self.mem.read(STATUS_SKILL_VANILLA, 4))
        if current != mask:
            self.mem.write32(STATUS_SKILL_VANILLA, mask)

    # ---- quality of life ----
    def set_qol(self, mask: int) -> None:
        """The quality-of-life options (QOL_* bits). Written every poll: the game clears it on a
        console reset."""
        current, = struct.unpack("<I", self.mem.read(STATUS_QOL, 4))
        if current != mask:
            self.mem.write32(STATUS_QOL, mask)

    def heartbeat(self) -> None:
        """Tells the game a client is polling: it then leaves the "Sent ..." popups to us."""
        self.ticks = (self.ticks + 1) & 0xFFFFFFFF or 1
        self.mem.write32(STATUS_CLIENT_TICKS, self.ticks)

    # ---- events ----
    def _read_event(self, seq: int, slot_count: int, slot_size: int) -> Optional[GameEvent]:
        raw = self.mem.read(MAILBOX + MAILBOX_HEADER.size + (seq % slot_count) * slot_size,
                            EVENT_SIZE)
        ev_seq, kind, item, location = EVENT_HEAD.unpack_from(raw)
        if ev_seq != seq:
            return None
        return GameEvent(seq, kind, item, location, game_text(raw[16:80]))

    def poll_events(self) -> List[GameEvent]:
        """New events since the last call. After a save-state load (the sequence going back or
        the newest event changing), everything still in the ring is returned again; location
        checks are idempotent, so duplicates are harmless and nothing is lost."""
        magic, write_seq, slot_count, slot_size = MAILBOX_HEADER.unpack(
            self.mem.read(MAILBOX, MAILBOX_HEADER.size))
        if magic != MAILBOX_MAGIC or slot_count != MAILBOX_SLOTS or slot_size != EVENT_SIZE:
            self.last_seq = 0            # nothing posted since boot
            self.last_event = None
            return []
        oldest = max(0, write_seq - slot_count)
        if (self.last_seq is None or write_seq < self.last_seq
                or self._rewound(write_seq, slot_count, slot_size)):
            start = oldest               # first poll, or a save state: re-read the whole ring
        else:
            start = self.last_seq
            if start < oldest:
                self.missed += oldest - start
                start = oldest
        events: List[GameEvent] = []
        for seq in range(start, write_seq):
            ev = self._read_event(seq, slot_count, slot_size)
            if ev is None:               # overwritten while we read
                self.missed += 1
                continue
            events.append(ev)
        self.last_seq = write_seq
        if write_seq > 0:
            ev = events[-1] if events and events[-1].seq == write_seq - 1 else \
                self._read_event(write_seq - 1, slot_count, slot_size)
            self.last_event = (ev.seq, ev.kind, ev.location) if ev else None
        return events

    def _rewound(self, write_seq: int, slot_count: int, slot_size: int) -> bool:
        """True when the newest event we saw is no longer what its slot holds, although newer
        events can't have overwritten it yet: a save state with another history was loaded."""
        if self.last_event is None:
            return False
        seq = self.last_event[0]
        if write_seq >= seq + 1 + slot_count:
            return False                 # legitimately overwritten by newer events
        ev = self._read_event(seq, slot_count, slot_size)
        return ev is None or (ev.seq, ev.kind, ev.location) != self.last_event

    # ---- items ----
    def sync_items(self, items: Sequence[Tuple[int, str]]) -> int:
        """Make the receive ring hold the server items the game still has to give.
        `items` = every item received from the server, in order: (game item ID, sender name).
        Returns `applied`, how many of them the loaded save already has."""
        header = self.mem.read(RECVQ, RECV_HEADER.size + RECV_SLOTS * RECV_ENTRY.size)
        magic, count, applied, _ = RECV_HEADER.unpack_from(header)
        total = len(items)
        if applied > total:
            # the save has more than the server sent so far (other seed, or items still on the
            # way after a reconnect); give nothing until the server catches up
            if magic == RECV_MAGIC and count != total:
                self.mem.write32(RECVQ + 4, total)
            return applied
        for n in range(applied, min(total, applied + RECV_SLOTS)):
            item, sender = items[n]
            entry = RECV_ENTRY.pack(n, item, encode_text(sender, SENDER_BYTES))
            off = RECV_HEADER.size + (n % RECV_SLOTS) * RECV_ENTRY.size
            if header[off:off + RECV_ENTRY.size] != entry:
                self.mem.write(RECVQ + off, entry)
        if count != total or magic != RECV_MAGIC:
            self.mem.write32(RECVQ + 4, total)      # count, after the entries are complete
        if magic != RECV_MAGIC:
            self.mem.write32(RECVQ, RECV_MAGIC)
        return applied

    # ---- torches ----
    def sync_torches(self, spots: Sequence[TorchSpot]) -> List[int]:
        """Make the game's torch table hold `spots` (empty: no table, every torch vanilla).
        Returns the game_keys of torches the game marked checked that `spots` doesn't have checked
        yet: breaking a red torch also posts an EV_LOCATION, so this is only a backstop for events
        the client missed (e.g. torches broken while it wasn't running).
        Checked flags are only ever set, never cleared. The whole table is rewritten when the
        layout changes or the game lost it (console reset), and re-read when the game bumps
        checked_seq and every TORCH_VERIFY_POLLS calls (a save-state load)."""
        magic, count, seq, _ = TORCH_HEADER.unpack(self.mem.read(TORCH_TABLE, TORCH_HEADER.size))
        if not spots:
            if magic == TORCH_TABLE_MAGIC:
                self.mem.write32(TORCH_TABLE, 0)
            self.torch_layout = None
            return []
        spots = spots[:TORCH_TABLE_MAX]
        layout = tuple(s.unchecked() for s in spots)
        if magic != TORCH_TABLE_MAGIC or count != len(spots) or layout != self.torch_layout:
            self._write_torch_table(spots, layout)
            return []
        found: List[int] = []
        self.torch_verify += 1
        if self.torch_verify >= TORCH_VERIFY_POLLS or seq != self.torch_seq:
            self.torch_verify = 0
            self.torch_seq = seq
            found = self._verify_torch_table(spots)
        for i, s in enumerate(spots):
            if s.checked and not self.torch_checked[i]:
                self.mem.write32(self._torch_flags_addr(i), TF_CHECKED)
                self.torch_checked[i] = True
        return found

    @staticmethod
    def _torch_flags_addr(i: int) -> int:
        return TORCH_TABLE + TORCH_HEADER.size + i * TORCH_ENTRY.size + TORCH_FLAGS_OFFSET

    def _write_torch_table(self, spots: Sequence[TorchSpot], layout: Tuple[TorchSpot, ...]) -> None:
        self.mem.write32(TORCH_TABLE, 0)          # the game ignores the table while we write it
        self.mem.write(TORCH_TABLE + TORCH_HEADER.size, b"".join(s.entry() for s in spots))
        self.mem.write(TORCH_TABLE + 4, struct.pack("<3I", len(spots), 0, 0))
        self.mem.write32(TORCH_TABLE, TORCH_TABLE_MAGIC)   # last
        self.torch_layout = layout
        self.torch_checked = [s.checked for s in spots]
        self.torch_verify = 0
        self.torch_seq = 0

    def _verify_torch_table(self, spots: Sequence[TorchSpot]) -> List[int]:
        """Re-read every entry: fix any that differ (a save state with another table, or one
        from before some checks) and learn the checked flags the game set. Returns the game_keys
        the game checked that `spots` doesn't have checked."""
        raw = self.mem.read(TORCH_TABLE + TORCH_HEADER.size, len(spots) * TORCH_ENTRY.size)
        found: List[int] = []
        for i, s in enumerate(spots):
            off = i * TORCH_ENTRY.size
            *fields, flags = TORCH_ENTRY.unpack_from(raw, off)
            same = tuple(fields) == (s.room_key, 0, s.x_bits, s.z_bits, s.game_key)
            game_checked = same and bool(flags & TF_CHECKED)   # another table's flag means nothing
            want = s.checked or game_checked
            if game_checked and not s.checked:
                found.append(s.game_key)
            if not same or bool(flags & TF_CHECKED) != want:
                entry = TorchSpot(s.room_key, s.x_bits, s.z_bits, s.game_key, want).entry()
                self.mem.write(TORCH_TABLE + TORCH_HEADER.size + off, entry)
            self.torch_checked[i] = want
        return found

    # ---- messages ----
    def post_message(self, text: str) -> bool:
        """Queue a popup (\\n line breaks, ^Crrggbbaa colour, ^c reset). False if the queue is full."""
        head, tail = MSGQ_HEADER.unpack(self.mem.read(MSGQ, MSGQ_HEADER.size))
        if (head - tail) & 0xFFFFFFFF >= MSGQ_SLOTS:
            return False
        data = encode_text(text, MSGQ_TEXT - 1) + b"\0"
        self.mem.write(MSGQ + MSGQ_HEADER.size + (head % MSGQ_SLOTS) * MSGQ_TEXT, data)
        self.mem.write32(MSGQ, (head + 1) & 0xFFFFFFFF)   # last: the box shows complete messages
        return True


def build_key_map(locations: Sequence[Dict]) -> Dict[int, int]:
    """game_key -> AP location ID, from data/locations.json records."""
    return {rec["game_key"]: rec["ap_id"] for rec in locations if rec.get("game_key") is not None}


def boss_game_key(iso_offset: int) -> int:
    """game_key of a boss reward location from its randomizer ISO offset (table @ 0x44F590)."""
    return BOSS_KEY_BASE + (iso_offset - 0x44F590) // 4
