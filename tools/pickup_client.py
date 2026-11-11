"""
Print item pickups and AP location checks from the "Archipelago Pickups" patch, read from PCSX2
over PINE.

PCSX2: Settings > Advanced > enable PINE (default slot 28011). On Windows PINE is a TCP server
on 127.0.0.1:<slot>. Protocol: every message is [u32 total size][commands...]; a read command
is [u8 opcode][u32 address]. The reply is [u32 total size][u8 result][values...], with the
values of a batch of commands simply concatenated.

usage: py -3.13 tools/pickup_client.py [--slot 28011]
"""
import argparse
import socket
import struct
import time

MSG_READ32 = 2
MSG_READ64 = 3
MSG_WRITE8 = 4
MSG_WRITE32 = 6
IPC_OK = 0

MAILBOX = 0x000FC000            # must match src/pickup.c
MAGIC = 0x50554B50              # "PKUP"
HEADER = struct.Struct('<4I')   # magic, write_seq, slot_count, slot_size
EV_PICKUP, EV_LOCATION = 0, 1   # event kinds, must match src/pickup.c


class Pine:
    def __init__(self, slot):
        self.sock = socket.create_connection(('127.0.0.1', slot))

    def _recv_exact(self, n):
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError('PCSX2 closed the PINE connection')
            data += chunk
        return data

    def _batch(self, commands):
        """Send several commands in one message; return the concatenated reply values."""
        body = b''.join(commands)
        self.sock.sendall(struct.pack('<I', 4 + len(body)) + body)
        size, = struct.unpack('<I', self._recv_exact(4))
        reply = self._recv_exact(size - 4)
        if reply[0] != IPC_OK:
            raise RuntimeError('PINE command failed (is a game running?)')
        return reply[1:]

    def read(self, addr, length):
        """Read `length` bytes (multiple of 8) with one batch of 64-bit reads."""
        cmds = [struct.pack('<BI', MSG_READ64, addr + off) for off in range(0, length, 8)]
        return self._batch(cmds)

    def write32(self, addr, value):
        self._batch([struct.pack('<BII', MSG_WRITE32, addr, value & 0xFFFFFFFF)])

    def write(self, addr, data):
        """Write bytes with one batch of 8-bit writes."""
        self._batch([struct.pack('<BIB', MSG_WRITE8, addr + i, b) for i, b in enumerate(data)])


def text(raw):
    """C string from the game: Shift-JIS (cp932) with the game's ^ control codes left in."""
    return raw.split(b'\0', 1)[0].decode('cp932', errors='replace')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--slot', type=int, default=28011)
    ap.add_argument('--interval', type=float, default=0.1, help='poll interval in seconds')
    args = ap.parse_args()

    try:
        pine = Pine(args.slot)
    except OSError as e:
        raise SystemExit(f'cannot connect to PINE on port {args.slot} ({e}); '
                         'enable PINE in PCSX2 (Settings > Advanced)')
    print(f'connected to PINE on port {args.slot}, watching mailbox at {MAILBOX:#x}')

    last_seq = None
    while True:
        magic, write_seq, slot_count, slot_size = HEADER.unpack(pine.read(MAILBOX, HEADER.size))
        if magic != MAGIC:
            last_seq = 0                   # no pickup yet (or mailbox reset by a reboot)
        elif last_seq is None:
            last_seq = write_seq           # start with what happens from now on
        else:
            if write_seq < last_seq:       # save state loaded with an older mailbox
                last_seq = write_seq
            if write_seq - last_seq > slot_count:
                print(f'(missed {write_seq - last_seq - slot_count} pickups)')
                last_seq = write_seq - slot_count
            for seq in range(last_seq, write_seq):
                ev_addr = MAILBOX + HEADER.size + (seq % slot_count) * slot_size
                ev = pine.read(ev_addr, slot_size)
                ev_seq, kind, item_id, location = struct.unpack_from('<Iiii', ev)
                if ev_seq != seq:
                    print(f'(pickup #{seq} was overwritten before it could be read)')
                    continue
                name = text(ev[16:80])
                if kind == EV_LOCATION:
                    print(f'#{seq}  LOCATION {location}  (vanilla item {item_id:02X} {name})')
                else:
                    print(f'#{seq}  item {item_id:02X}  {name}')
                    print(f'    {text(ev[80:256])}'.replace('\n', '\n    '))
            last_seq = write_seq
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
