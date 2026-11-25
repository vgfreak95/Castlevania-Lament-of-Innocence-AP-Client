"""Minimal PINE client for PCSX2 (EE memory reads/writes over a local socket).

PCSX2: Settings > Advanced > PINE, default slot 28011. On Windows PINE is a TCP server on
127.0.0.1:<slot>. On Linux and macOS it is a Unix socket (PCSX2's PINE.cpp): pcsx2.sock in
$XDG_RUNTIME_DIR (Linux; /tmp without it) or $TMPDIR (macOS), named pcsx2.sock.<slot> for a slot
other than 28011. The AppImage only has that socket; the Flatpak's is under
$XDG_RUNTIME_DIR/app/net.pcsx2.PCSX2/. Pine tries an explicit socket path first, then those
default paths, then TCP (which also covers a socket forwarded with socat).
Every message is [u32 total size][commands...]; the reply is
[u32 total size][u8 result][values...], the values of a batch simply concatenated.

No Archipelago imports: the protocol tests run this against a fake socket.
"""
from __future__ import annotations

import os
import posixpath
import socket
import struct
import sys
import tempfile
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

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


SOCKET_NAME = "pcsx2.sock"
FLATPAK_DIR = "app/net.pcsx2.PCSX2"


def unix_sockets_supported() -> bool:
    return hasattr(socket, "AF_UNIX") and sys.platform != "win32"


def default_socket_paths(slot: int = DEFAULT_SLOT, env: Optional[Mapping[str, str]] = None,
                         platform: Optional[str] = None) -> List[str]:
    """Where PCSX2 puts its PINE socket for `slot` (Linux/macOS; none on Windows)."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return []
    name = SOCKET_NAME if slot == DEFAULT_SLOT else f"{SOCKET_NAME}.{slot}"
    if platform == "darwin":
        dirs = [env.get("TMPDIR") or tempfile.gettempdir()]
    else:
        runtime = env.get("XDG_RUNTIME_DIR")
        dirs = [runtime, posixpath.join(runtime, FLATPAK_DIR)] if runtime else []
        dirs.append("/tmp")
    paths: List[str] = []
    for d in dirs:
        path = posixpath.join(d, name)   # POSIX paths only (no sockets on Windows)
        if path not in paths:
            paths.append(path)
    return paths


class Pine:
    def __init__(self, slot: int = DEFAULT_SLOT, host: str = "127.0.0.1", timeout: float = 2.0,
                 socket_path: Optional[str] = None):
        self.slot = slot
        self.host = host
        self.timeout = timeout
        self.socket_path = socket_path      # explicit Unix socket; None = the default paths
        self.sock: Optional[socket.socket] = None
        self.endpoint = ""                  # what the last connect() reached, for messages

    # ---- connection ----
    def connect(self) -> None:
        """Connect over PCSX2's Unix socket when there is one, else over TCP 127.0.0.1:<slot>.
        An explicit socket_path is used alone (no TCP fallback)."""
        self.close()
        errors: List[str] = []
        if unix_sockets_supported():
            paths = [self.socket_path] if self.socket_path else default_socket_paths(self.slot)
            for path in paths:
                if not self.socket_path and not os.path.exists(path):
                    continue
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                try:
                    sock.connect(path)
                except OSError as exc:
                    sock.close()
                    errors.append(f"socket {path}: {exc}")
                    continue
                self.sock, self.endpoint = sock, f"socket {path}"
                return
            if self.socket_path:
                raise PineError(f"cannot connect to PCSX2 PINE ({errors[0]})")
        elif self.socket_path:
            raise PineError("Unix sockets aren't available on this system; use the PINE slot")
        try:
            sock = socket.create_connection((self.host, self.slot), timeout=self.timeout)
        except OSError as exc:
            errors.append(f"port {self.slot}: {exc}")
            raise PineError("cannot connect to PCSX2 PINE (" + "; ".join(errors) + ")") from exc
        sock.settimeout(self.timeout)
        self.sock, self.endpoint = sock, f"port {self.slot}"

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
