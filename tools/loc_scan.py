"""
Fill `game_key` in apworld/lament_of_innocence/data/locations.json from the in-game location scan.

1. In the game (debug pnach, "Debug printf" and "Archipelago Pickups" on): debug menu >
   AP location scan > Scan all rooms. Every placed item that spawns logs
     [locscan] stage S room R key K flag F item II pos X Y Z bits XXXXXXXX YYYYYYYY ZZZZZZZZ game_key G
   to the EE console (PCSX2 also writes it to its log file, emulog.txt).
2. py -3.13 tools/loc_scan.py --iso "<path to the LoI ISO>" --log "<path to emulog.txt>"

Each pickup location's randomizer `iso_offset` points at the item ID inside a 0x80-byte actor
record that starts 0x10 earlier: u16 class at +2 (0x54 = placed item), item at +0x10,
param at +0x14 (low 16 bits kind, high 16 bits collected-flag index + 1, 0 = not persistent),
position at +0x60. The record's item, flag and position are matched against the logged spawns,
which give the room key; game_key = room_key * 64 + flag. Positions are compared bit-exact first
(several rooms have the same item and flag at the same rounded position), then rounded. Boss locations get
0x8000 + their index in the boss reward table (ISO 0x44F590), no scan needed.

usage: py -3.13 tools/loc_scan.py --iso ISO [--log LOG ...] [--locations JSON] [--dry-run]
       py -3.13 tools/loc_scan.py --iso ISO --check     (ISO records only, no log)
"""
import argparse
import json
import os
import re
import struct
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LOCATIONS = os.path.join(ROOT, "apworld", "lament_of_innocence", "data", "locations.json")

RECORD_BEFORE_ITEM = 0x10
RECORD_SIZE = 0x80
CLASS_PLACED_ITEM = 0x54
BOSS_TABLE_ISO = 0x44F590
BOSS_KEY_BASE = 0x8000
POS_TOLERANCE = 2.0          # the log prints positions truncated to integers

LINE = re.compile(r"\[locscan\] stage (\d+) room (\d+) key (\d+) flag (-?\d+) item ([0-9A-Fa-f]+) "
                  r"pos (-?\d+) (-?\d+) (-?\d+)(?: bits ([0-9A-Fa-f]{8}) ([0-9A-Fa-f]{8}) "
                  r"([0-9A-Fa-f]{8}))?")


def read_record(iso, iso_offset):
    """(class, item, flag, (x, y, z), raw position bits) of the actor record holding `iso_offset`."""
    iso.seek(iso_offset - RECORD_BEFORE_ITEM)
    rec = iso.read(RECORD_SIZE)
    if len(rec) != RECORD_SIZE:
        raise ValueError(f"offset {iso_offset:#x} is past the end of the ISO")
    cls, = struct.unpack_from("<H", rec, 2)
    item, param = struct.unpack_from("<iI", rec, 0x10)
    pos = struct.unpack_from("<3f", rec, 0x60)
    bits = struct.unpack_from("<3I", rec, 0x60)
    return cls, item, (param >> 16) - 1, pos, bits


def parse_logs(paths):
    """Spawns from the EE console logs: list of dicts, duplicates (room visited twice) removed."""
    seen, out = set(), []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = LINE.search(line)
                if not m:
                    continue
                stage, room, key, flag = (int(m.group(i)) for i in range(1, 5))
                item = int(m.group(5), 16)
                pos = tuple(int(m.group(i)) for i in range(6, 9))
                bits = tuple(int(m.group(i), 16) for i in range(9, 12)) if m.group(9) else None
                ident = (key, flag, item, pos, bits)
                if ident in seen:
                    continue
                seen.add(ident)
                out.append(dict(stage=stage, room=room, key=key, flag=flag, item=item, pos=pos,
                                bits=bits))
    return out


def close(a, b):
    return all(abs(x - y) <= POS_TOLERANCE for x, y in zip(a, b))


def match(locations, iso_path, spawns, check_only=False):
    """Returns ({ap_id: game_key}, [problems])."""
    by_item_flag = defaultdict(list)
    for s in spawns:
        by_item_flag[(s["item"], s["flag"])].append(s)
    keys, problems = {}, []
    with open(iso_path, "rb") as iso:
        for loc in locations:
            name = loc["name"]
            if loc["kind"] == "boss":
                keys[loc["ap_id"]] = BOSS_KEY_BASE + (loc["iso_offset"] - BOSS_TABLE_ISO) // 4
                continue
            cls, item, flag, pos, bits = read_record(iso, loc["iso_offset"])
            desc = f"{name} (iso {loc['iso_offset']:#x}: item {item:02X} flag {flag} " \
                   f"pos {pos[0]:.0f} {pos[1]:.0f} {pos[2]:.0f})"
            if cls != CLASS_PLACED_ITEM or item != loc["vanilla_item"]:
                problems.append(f"{desc}: not a placed-item record (class {cls:#x}, expected item "
                                f"{loc['vanilla_item']:02X})")
                continue
            if flag < 0:
                problems.append(f"{desc}: no collected flag (respawning item); the runtime patch "
                                "can't make it a location")
                continue
            if check_only:
                continue
            cands = by_item_flag.get((item, flag), [])
            exact = [s for s in cands if s["bits"] == bits]
            near = exact or [s for s in cands if close(s["pos"], pos)]
            rooms = {s["key"] for s in near}
            if len(rooms) == 1:
                keys[loc["ap_id"]] = near[0]["key"] * 64 + flag
            elif len(rooms) > 1:
                problems.append(f"{desc}: ambiguous, rooms " +
                                ", ".join(f"{s['stage']}/{s['room']}" for s in near))
            elif len({s["key"] for s in cands}) == 1:
                s = cands[0]
                keys[loc["ap_id"]] = s["key"] * 64 + flag
                problems.append(f"{desc}: matched stage {s['stage']} room {s['room']} by item and "
                                f"flag only (spawn pos {s['pos']}); check it")
            elif cands:
                problems.append(f"{desc}: no spawn at this position; same item+flag in rooms " +
                                ", ".join(f"{s['stage']}/{s['room']} pos {s['pos']}" for s in cands))
            else:
                problems.append(f"{desc}: never seen in the scan")
    return keys, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--iso", required=True, help="Castlevania - Lament of Innocence (USA) ISO")
    ap.add_argument("--log", action="append", default=[], help="EE console log(s) with the scan")
    ap.add_argument("--locations", default=DEFAULT_LOCATIONS)
    ap.add_argument("--dry-run", action="store_true", help="report only, don't write the JSON")
    ap.add_argument("--check", action="store_true", help="only check the ISO records")
    ap.add_argument("--bosses-only", action="store_true",
                    help="write the boss keys only (they need no scan)")
    args = ap.parse_args()

    with open(args.locations, encoding="utf-8") as f:
        raw = f.read()
    locations = json.loads(raw)
    spawns = parse_logs(args.log)
    if not args.check and not args.bosses_only and not spawns:
        sys.exit("no [locscan] lines in the log(s); run the in-game scan first (see --help)")
    keys, problems = match(locations, args.iso, spawns, check_only=args.check)

    pickups = sum(1 for loc in locations if loc["kind"] != "boss")
    found = sum(1 for loc in locations if loc["kind"] != "boss" and loc["ap_id"] in keys)
    print(f"{len(spawns)} spawns in the log; {found}/{pickups} pickups matched, "
          f"{sum(1 for loc in locations if loc['kind'] == 'boss')} boss keys")
    for p in problems:
        if not args.bosses_only:
            print("  " + p)
    if args.check or args.dry_run:
        return
    changed = 0
    for loc in locations:
        key = keys.get(loc["ap_id"])
        if key is not None and loc.get("game_key") != key:
            loc["game_key"] = key
            changed += 1
    dup = defaultdict(list)
    for loc in locations:
        if loc.get("game_key") is not None:
            dup[loc["game_key"]].append(loc["name"])
    for key, names in dup.items():
        if len(names) > 1:
            print(f"  WARNING: game_key {key} used by {', '.join(names)}")
    with open(args.locations, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(locations, indent=2, ensure_ascii=False))
        if raw.endswith("\n"):
            f.write("\n")
    print(f"{changed} game_key values written to {args.locations}")


if __name__ == "__main__":
    main()
