"""Minimal PINE client for PCSX2 (EE memory reads/writes over a local socket).

PCSX2: Settings > Advanced > PINE, default slot 28011. On Windows PINE is a TCP server on
127.0.0.1:<slot>. Every message is [u32 total size][commands...]; the reply is
[u32 total size][u8 result][values...], the values of a batch simply concatenated.

No Archipelago imports: the protocol tests run this against a fake socket.
"""
from __future__ import annotations

import socket
import struct
from typing import Iterable, List, Optional, Sequence, Tuple

DEFAULT_SLOT = 28011

READ8, READ16, READ32, READ64 = 0x00, 0x01, 0x02, 0x03
WRITE8, WRITE16, WRITE32, WRITE64 = 0x04, 0x05, 0x06, 0x07
VERSION, TITLE, ID, UUID, GAME_VERSION, STATUS = 0x08, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F
IPC_OK, IPC_FAIL = 0x00, 0xFF

EMU_RUNNING, EMU_PAUSED, EMU_SHUTDOWN = 0, 1, 2

MAX_BATCH = 4096          # commands per message; keeps replies far below PCSX2's buffer
MAX_REPLY = 1 << 20


class PineError(ConnectionError):
    """PCSX2 is not reachable, closed the connection, or rejected a command."""


class Pine:
    def __init__(self, slot: int = DEFAULT_SLOT, host: str = "127.0.0.1", timeout: float = 2.0):
        self.slot = slot
        self.host = host
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    # ---- connection ----
    def connect(self) -> None:
        self.close()
        try:
            sock = socket.create_connection((self.host, self.slot), timeout=self.timeout)
        except OSError as exc:
            raise PineError(f"cannot connect to PCSX2 PINE on port {self.slot}: {exc}") from exc
        sock.settimeout(self.timeout)
        self.sock = sock

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    @property
    def connected(self) -> bool:
        return self.sock is not None

    # ---- transport ----
    def _recv_exact(self, n: int) -> bytes:
        assert self.sock is not None
        data = bytearray()
        while len(data) < n:
            try:
                chunk = self.sock.recv(n - len(data))
            except OSError as exc:
                self.close()
                raise PineError(f"lost the PINE connection: {exc}") from exc
            if not chunk:
                self.close()
                raise PineError("PCSX2 closed the PINE connection")
            data += chunk
        return bytes(data)

    def _request(self, commands: Sequence[bytes]) -> bytes:
        if self.sock is None:
            raise PineError("not connected to PCSX2")
        body = b"".join(commands)
        try:
            self.sock.sendall(struct.pack("<I", 4 + len(body)) + body)
        except OSError as exc:
            self.close()
            raise PineError(f"lost the PINE connection: {exc}") from exc
        size, = struct.unpack("<I", self._recv_exact(4))
        if size < 5 or size > MAX_REPLY:
            self.close()
            raise PineError(f"bad PINE reply size {size}")
        reply = self._recv_exact(size - 4)
        if reply[0] != IPC_OK:
            raise PineError("PCSX2 rejected the PINE command (is a game running?)")
        return reply[1:]

    def batch(self, commands: Sequence[bytes]) -> bytes:
        """Send commands in as few messages as allowed; return the concatenated values."""
        out = bytearray()
        for start in range(0, len(commands), MAX_BATCH):
            out += self._request(commands[start:start + MAX_BATCH])
        return bytes(out)

    # ---- memory ----
    def read(self, addr: int, length: int) -> bytes:
        """Read `length` bytes. Uses 64-bit reads for the aligned middle, 8-bit reads at the edges."""
        cmds: List[bytes] = []
        sizes: List[int] = []
        a, end = addr, addr + length
        while a < end:
            if a % 8 == 0 and end - a >= 8:
                cmds.append(struct.pack("<BI", READ64, a))
                sizes.append(8)
                a += 8
            else:
                cmds.append(struct.pack("<BI", READ8, a))
                sizes.append(1)
                a += 1
        data = self.batch(cmds)
        if len(data) != sum(sizes):
            raise PineError("short PINE read reply")
        return data

    def read32(self, addr: int) -> int:
        return struct.unpack("<I", self.batch([struct.pack("<BI", READ32, addr)]))[0]

    def read16(self, addr: int) -> int:
        return struct.unpack("<H", self.batch([struct.pack("<BI", READ16, addr)]))[0]

    def write(self, addr: int, data: bytes) -> None:
        """Write bytes in order: 32-bit writes where aligned, 8-bit writes at the edges."""
        cmds: List[bytes] = []
        i = 0
        while i < len(data):
            a = addr + i
            if a % 4 == 0 and len(data) - i >= 4:
                cmds.append(struct.pack("<BI", WRITE32, a) + data[i:i + 4])
                i += 4
            else:
                cmds.append(struct.pack("<BIB", WRITE8, a, data[i]))
                i += 1
        if cmds:
            self.batch(cmds)

    def write32(self, addr: int, value: int) -> None:
        self.batch([struct.pack("<BII", WRITE32, addr, value & 0xFFFFFFFF)])

    def write32_many(self, writes: Iterable[Tuple[int, int]]) -> None:
        cmds = [struct.pack("<BII", WRITE32, a, v & 0xFFFFFFFF) for a, v in writes]
        if cmds:
            self.batch(cmds)

    # ---- emulator info ----
    def _string(self, opcode: int) -> str:
        data = self.batch([struct.pack("<B", opcode)])
        if len(data) < 4:
            raise PineError("short PINE string reply")
        n, = struct.unpack_from("<I", data)
        return data[4:4 + n].split(b"\0", 1)[0].decode("ascii", "replace")

    def game_id(self) -> str:
        return self._string(ID)

    def title(self) -> str:
        return self._string(TITLE)

    def status(self) -> int:
        data = self.batch([struct.pack("<B", STATUS)])
        if len(data) != 4:
            raise PineError("bad PINE status reply")
        return struct.unpack("<I", data)[0]
