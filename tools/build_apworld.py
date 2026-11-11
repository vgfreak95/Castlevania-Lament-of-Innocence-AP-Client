"""Zips apworld/lament_of_innocence into build/lament_of_innocence.apworld.

Usage: py -3.13 tools/build_apworld.py [--install] [--dev PATH]
  --install   also copy the .apworld into C:\\ProgramData\\Archipelago\\custom_worlds
  --dev PATH  also refresh an Archipelago source checkout: mirror the world folder into
              PATH/worlds/lament_of_innocence (for Generate.py and the unit tests) and copy the
              .apworld to PATH/worlds/lament_of_innocence.apworld (for the Launcher)

The .apworld leaves out the world's test/ folder: players don't need it, and with both the zip
and the folder in a checkout's worlds/, pytest would otherwise find the same test module twice.
"""
import argparse
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLD = ROOT / "apworld" / "lament_of_innocence"
OUT = ROOT / "build" / "lament_of_innocence.apworld"
CUSTOM_WORLDS = Path(r"C:\ProgramData\Archipelago\custom_worlds")
CONTAINER_VERSION = 7          # worlds/Files.py container_version in AP 0.6.x
SKIP_DIRS = {"__pycache__", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def files(skip_dirs=SKIP_DIRS):
    for p in sorted(WORLD.rglob("*")):
        if p.is_dir() or skip_dirs & set(p.relative_to(WORLD).parts) or p.suffix in SKIP_SUFFIXES:
            continue
        yield p


def mirror(dst: Path) -> None:
    """Copy the world folder over dst file by file, removing files that no longer exist. A file
    another program has open (e.g. a doc in an editor) is skipped with a warning instead of
    leaving a half-deleted copy."""
    wanted = {p.relative_to(WORLD) for p in files()}
    for rel in sorted(wanted):
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(WORLD / rel, target)
        except PermissionError:
            print(f"  skipped {target} (in use)")
    for p in sorted(dst.rglob("*"), reverse=True):
        rel = p.relative_to(dst)
        if p.is_file() and rel not in wanted and not SKIP_DIRS & set(rel.parts):
            p.unlink()
        elif p.is_dir() and not SKIP_DIRS & set(rel.parts) and not any(p.iterdir()):
            p.rmdir()


def build() -> Path:
    manifest = json.loads((WORLD / "archipelago.json").read_text(encoding="utf-8"))
    manifest["version"] = CONTAINER_VERSION
    manifest["compatible_version"] = CONTAINER_VERSION
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files(SKIP_DIRS | {"test"}):
            arc = f"{WORLD.name}/{p.relative_to(WORLD).as_posix()}"
            if p.name == "archipelago.json" and p.parent == WORLD:
                z.writestr(arc, json.dumps(manifest, indent=2))
            else:
                z.write(p, arc)
    return OUT


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--dev", type=Path)
    args = ap.parse_args()
    out = build()
    with zipfile.ZipFile(out) as z:
        print(f"built {out} ({len(z.namelist())} files)")
    if args.install:
        shutil.copy2(out, CUSTOM_WORLDS / out.name)
        print(f"installed to {CUSTOM_WORLDS / out.name}")
    if args.dev:
        dst = args.dev / "worlds" / WORLD.name
        mirror(dst)
        print(f"mirrored to {dst}")
        zip_dst = args.dev / "worlds" / out.name
        try:
            shutil.copy2(out, zip_dst)
            print(f"copied to {zip_dst}")
        except PermissionError:
            print(f"  could not replace {zip_dst} (in use: close the Launcher and run again)")


if __name__ == "__main__":
    main()
