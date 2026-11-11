"""Game side of the Lament of Innocence AP client: the RAM protocol of the "Archipelago Pickups"
patch (src/pickup.c, src/msgbox.h, src/ap.h), spoken over PINE.

- Event mailbox @ 0xFC000: the game reports location checks (EV_LOCATION, location = game_key).
- Status block @ 0xFCF00: protocol version, goal bits, location-scan flag, client heartbeat.
- Message queue @ 0xFD000: the client may post popups ("Sent X to Y").
- Receive ring @ 0xFE000: the client writes the server's items; the game gives them in order and
  keeps how many it has given (`applied`) in the save.

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
STATUS_STRUCT = struct.Struct("<5I")  # magic, version, goal, scan, client_ticks
STATUS_MAGIC = 0x54535041           # "APST"
PROTOCOL_VERSION = 2
STATUS_CLIENT_TICKS = STATUS + 16
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


@dataclass
class GameStatus:
    goal: int
    scan: bool
    stage: int
    room: int


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
        raw = self.mem.read(STATUS, STATUS_STRUCT.size + 4)   # 20 bytes, read as 24
        magic, _version, goal, scan, _ticks = STATUS_STRUCT.unpack_from(raw)
        stage, room = struct.unpack("<2H", self.mem.read(CUR_STAGE, 4))
        if magic != STATUS_MAGIC:
            goal, scan = 0, 0
        return GameStatus(goal=goal, scan=scan == 0x4E414353, stage=stage, room=room)

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
