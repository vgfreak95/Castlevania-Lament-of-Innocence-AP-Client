"""
Build apworld/lament_of_innocence/data/torches.json (the Torch Sanity locations) from the debug
menu's torch scan.

1. In the game (debug pnach with the Archipelago Pickups patch): debug menu > Torches > Scan all
   rooms, then in the debug tools checkout:
     py -3 tools/torch_rando.py scan --out torches.json
   (or torch_rando.py from-log emulog.txt, with "Log torches as they spawn" on during the scan)
2. py -3.13 tools/gen_torch_locations.py ../Castlevania-Lament-of-Innocence-Debug-Tools/torches.json

A torch is identified in game by its room key and spawn position (x/z float bits; src/torches.c).
Weapon torches (sub-weapon drops 0xAA-0xAF) are left out: they keep their vanilla drop.
ap_id and game_key are kept for torches already in the output file, so regenerating never
renumbers a location; new torches get the next free numbers.

usage: py -3.13 tools/gen_torch_locations.py SCAN_JSON [--out PATH] [--dry-run]
"""
import argparse
import json
import os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "apworld", "lament_of_innocence", "data", "torches.json")

TORCH_BASE_ID = 207350000      # data_loader.TORCH_BASE_ID: ap_id = TORCH_BASE_ID + n
TORCH_KEY_BASE = 0x10000       # src/torches.h TORCH_KEY_BASE: game_key = TORCH_KEY_BASE + n

# stage -> AP region (regions.py AREAS), from the stages of the existing locations' room keys
STAGE_REGION = {0: "HoSR", 1: "ASML", 2: "DPoW", 3: "GFbT", 5: "PotMM", 6: "PoET", 7: "PttDA",
                8: "Theatre"}


def num(v):
    return int(v, 16) if isinstance(v, str) else int(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scan")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.scan, encoding="utf-8") as f:
        scan = json.load(f)

    old = {}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            for rec in json.load(f):
                old[(rec["room_key"], rec["x_bits"], rec["z_bits"])] = rec
    next_n = max((rec["ap_id"] - TORCH_BASE_ID for rec in old.values()), default=-1) + 1

    torches = sorted((t for t in scan if not t["weapon_torch"]), key=lambda t: (t["key"], t["index"]))
    skipped = Counter()
    per_room = defaultdict(int)
    out = []
    for t in torches:
        region = STAGE_REGION.get(t["stage"])
        if region is None:
            skipped[t["stage"]] += 1
            continue
        per_room[t["key"]] += 1
        ident = (t["key"], num(t["x_bits"]), num(t["z_bits"]))
        prev = old.get(ident)
        if prev:
            n = prev["ap_id"] - TORCH_BASE_ID
        else:
            n, next_n = next_n, next_n + 1
        out.append({
            "name": f"{region}: Room {t['room']} Torch {per_room[t['key']]}",
            "ap_id": TORCH_BASE_ID + n,
            "region": region,
            "kind": "torch",
            "vanilla_item": num(t["item"]),
            "stage": t["stage"],
            "room": t["room"],
            "room_key": t["key"],
            "x_bits": ident[1],
            "z_bits": ident[2],
            "game_key": TORCH_KEY_BASE + n,
        })
    out.sort(key=lambda r: r["ap_id"])
    names = Counter(r["name"] for r in out)
    dupes = [n for n, c in names.items() if c > 1]
    if dupes:
        raise SystemExit(f"duplicate location names: {dupes[:5]}")
    gone = len(set(old) - {(r["room_key"], r["x_bits"], r["z_bits"]) for r in out})

    print(f"{len(out)} torch locations ({sum(t['weapon_torch'] for t in scan)} weapon torches left out)")
    print("  per region:", dict(sorted(Counter(r["region"] for r in out).items())))
    if skipped:
        print("  skipped, stage without a region:", dict(skipped))
    if gone:
        print(f"  WARNING: {gone} torches of the old file are not in this scan (their IDs are dropped)")
    if args.dry_run:
        return
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
