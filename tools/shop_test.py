"""
Shop Sanity test without a seed: writes a sample shop table (src/apshop.h, 0xB4000) into the game
over PINE, the way the AP client does, or shows / clears the one there.

usage: py -3.13 tools/shop_test.py fill [N] [--vanilla HEX] [--price GOLD] [--long] [--slot 28011]
       py -3.13 tools/shop_test.py show [--slot 28011]
       py -3.13 tools/shop_test.py clear [--slot 28011]

`fill` makes N AP slots (default 25: more than the 20 shown at once), cycling through the three
looks, with prices GOLD, GOLD+10, ...; --vanilla sets which vanilla items stay (bit i =
game_interface.SHOP_VANILLA_ITEMS[i], default 7FFF = all); --long uses long names to check the
row width. Buying a slot in game sets its checked flag (see `show`) and posts an EV_LOCATION
(tools/pickup_client.py shows it). Open the shop after writing: the list is built when it opens.
"""
import argparse
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "apworld", "lament_of_innocence")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"loi_{name}", os.path.join(PKG, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pine = _load("pine")
gi = _load("game_interface")

SAMPLES = [("Hookshot", "Alice", False), ("Whip of Flames", "Leon", True), ("Bomb Bag", "Bob", False),
           ("Progressive Sword", "Zelda", False), ("Potion", "Leon", True)]
LONG = ("Progressive Armor Upgrade Level", "LongPlayerName16", False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fill", "show", "clear"])
    ap.add_argument("n", nargs="?", type=int, default=25)
    ap.add_argument("--vanilla", default="7FFF")
    ap.add_argument("--price", type=int, default=100)
    ap.add_argument("--long", action="store_true")
    ap.add_argument("--slot", type=int, default=pine.DEFAULT_SLOT)
    args = ap.parse_args()

    p = pine.Pine(args.slot)
    p.connect()
    iface = gi.LoIInterface(p)
    if args.cmd == "clear":
        iface.sync_shop(False, 0, [])
        print("shop table cleared (vanilla shop)")
        return
    if args.cmd == "show":
        raw = p.read(gi.SHOP_TABLE, gi.SHOP_HEADER.size)
        magic, count, vanilla, seq = gi.SHOP_HEADER.unpack(raw)[:4]
        if magic != gi.SHOP_TABLE_MAGIC:
            print("no shop table")
            return
        print(f"{count} slots, vanilla {vanilla:04X}, checked_seq {seq}")
        for i in range(min(count, gi.SHOP_SLOTS_MAX)):
            s = gi.SHOP_SLOT.unpack(p.read(gi.SHOP_TABLE + gi.SHOP_HEADER.size + i * gi.SHOP_SLOT.size,
                                           gi.SHOP_SLOT.size))
            print(f"  {i:2} key {s[0]:05X} {s[1]:5}g look {s[2]} checked {s[3]} report {s[4]}  "
                  f"{gi.game_text(s[8])!r}")
        return
    slots = []
    for i in range(min(args.n, gi.SHOP_SLOTS_MAX)):
        item, player, own = LONG if args.long else SAMPLES[i % len(SAMPLES)]
        flags = [gi.AP_FLAG_PROGRESSION, gi.AP_FLAG_USEFUL, 0][i % 3]
        name, desc = gi.shop_texts(f"{item} {i}" if not args.long else item, player, own, flags)
        slots.append(gi.ShopEntry(gi.shop_game_key(i), args.price + 10 * i, gi.shop_look(flags),
                                  name, desc))
    iface.sync_shop(True, int(args.vanilla, 16), slots)
    print(f"wrote {len(slots)} AP shop slots, vanilla {int(args.vanilla, 16):04X}")


if __name__ == "__main__":
    main()
