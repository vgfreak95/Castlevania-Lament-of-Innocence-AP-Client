"""
Fake AP server: send one item to the game through the receive ring of the "Archipelago Pickups"
patch (src/pickup.c), over PINE.

usage: py -3.13 tools/send_item.py <item id hex> [sender] [--slot 28011]
   e.g. py -3.13 tools/send_item.py 2A Player2      -> "Received Potion from Player2"
"""
import argparse
import struct

from pickup_client import Pine

RECVQ = 0x000FE000              # must match src/pickup.c
RECV_MAGIC = 0x56434552         # "RECV"
RECV_SLOTS = 16
HEADER = struct.Struct('<4I')   # magic, count, applied, reserved
ENTRY = struct.Struct('<Ii24s') # index, item, sender


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('item', help='item ID in hex (see lament_item_table.md)')
    ap.add_argument('sender', nargs='?', default='Player2')
    ap.add_argument('--slot', type=int, default=28011)
    args = ap.parse_args()

    pine = Pine(args.slot)
    magic, count, applied, _ = HEADER.unpack(pine.read(RECVQ, HEADER.size))
    if magic != RECV_MAGIC:
        count = 0
    index = max(count, applied)     # a real client would use its own item list instead
    if index - applied >= RECV_SLOTS:
        raise SystemExit(f'{index - applied} items still waiting in the game; try again later')

    entry = ENTRY.pack(index, int(args.item, 16), args.sender.encode('ascii')[:23])
    pine.write(RECVQ + HEADER.size + (index % RECV_SLOTS) * ENTRY.size, entry)
    pine.write32(RECVQ + 4, index + 1)        # count, after the entry is complete
    pine.write32(RECVQ, RECV_MAGIC)
    print(f'sent item #{index}: {args.item.upper()} from {args.sender} (game has applied {applied})')


if __name__ == '__main__':
    main()
