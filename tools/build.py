"""
Build every patch in config.toml and write the pnaches; optionally install one into PCSX2.

usage: py -3 tools/build.py [--install [PNACH]]   (Windows: .\\build.ps1 [-Install] [-Practice])
       python3 tools/build.py [--install [PNACH]]

Compiles with build.sh, in the [build] docker_image container or, when that is "", with the PS2
toolchain on PATH. --install copies [pnach.PNACH] (default: [install] pnach) to the PCSX2 patches
folder ([install] patches_dir, or PCSX2's default for this OS).

Patches can come from another checkout next to this one, so shared code lives in one place:
    [import.ap]
    config = "../Castlevania-Lament-of-Innocence-AP-Client/config.toml"
    patches = ["pickup", "minimap"]
adds those [patch.*] tables as if they were written here, with their sources rewritten relative
to this folder. The imported checkout's tools/gen_ap_locations.py (if any) runs before compiling.
The Docker build mounts the parent folder, so these ../ paths resolve inside the container too.
This file is the same in both checkouts; keep it that way.
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit('tools/build.py needs Python 3.11 or newer (for tomllib)')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import bin2pnach  # noqa: E402


def run_generator(checkout):
    """Runs <checkout>/tools/gen_ap_locations.py (src/ap_locations.h, for pickup.c), if present."""
    path = checkout / 'tools' / 'gen_ap_locations.py'
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location(f'gen_ap_locations_{checkout.name}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.generate()


def import_patches(config):
    """Adds the [patch.*] tables listed under [import.*] from other checkouts' config.toml."""
    for key, imp in config.get('import', {}).items():
        other_config = (ROOT / imp['config']).resolve()
        other_root = other_config.parent
        with open(other_config, 'rb') as f:
            other = tomllib.load(f)
        prefix = Path(os.path.relpath(other_root, ROOT)).as_posix()
        for name in imp['patches']:
            if name not in other.get('patch', {}):
                sys.exit(f'[import.{key}]: no [patch.{name}] in {other_config}')
            if name in config['patch']:
                sys.exit(f'[import.{key}]: [patch.{name}] is also defined here')
            patch = dict(other['patch'][name])
            patch['sources'] = [f'{prefix}/{s}' for s in patch['sources']]
            config['patch'][name] = patch
        run_generator(other_root)


def expand_sources(sources):
    """Source paths, with wildcards ("src/submenus/*.c") expanded in sorted order."""
    files = []
    for source in sources:
        if any(c in source for c in '*?['):
            matches = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob(source))
            if not matches:
                sys.exit(f'sources: nothing matches {source}')
            files += matches
        else:
            files.append(source)
    return files


def write_patch_list(config):
    """build/patches.txt, read by build.sh: '<name> <base> <cflags and sources...>' per line."""
    lines = []
    for name, patch in config['patch'].items():
        args = patch.get('cflags', []) + expand_sources(patch['sources'])
        lines.append(f"{name} {patch['base']:#010x} {' '.join(args)}")
    (ROOT / 'build').mkdir(exist_ok=True)
    with open(ROOT / 'build' / 'patches.txt', 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


def compile_patches(config):
    image = config['build']['docker_image']
    if image:
        # the parent folder, so sources imported from a neighbouring checkout (../...) are visible
        cmd = ['docker', 'run', '--rm', '-v', f'{ROOT.parent}:/work', '-w', f'/work/{ROOT.name}']
        if hasattr(os, 'getuid'):  # Linux/macOS: build/ files owned by the user, not root
            cmd += ['-u', f'{os.getuid()}:{os.getgid()}']
        cmd += [image, 'sh', 'build.sh']
    else:
        cmd = ['sh', 'build.sh']
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        sys.exit('compile failed')


def default_patches_dir():
    home = Path.home()
    if sys.platform == 'win32':
        return home / 'Documents' / 'PCSX2' / 'patches'
    if sys.platform == 'darwin':
        return home / 'Library' / 'Application Support' / 'PCSX2' / 'patches'
    return home / '.config' / 'PCSX2' / 'patches'


def install(config, pnach_name, path):
    dest_dir = config['install']['patches_dir'] or default_patches_dir()
    dest = Path(dest_dir) / path.name
    shutil.copyfile(path, dest)
    print(f'Installed {pnach_name} ({path}) to {dest}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='config.toml')
    ap.add_argument('--install', nargs='?', const='', metavar='PNACH',
                    help='copy this pnach (default: [install] pnach) into PCSX2')
    args = ap.parse_args()

    os.chdir(ROOT)
    config = bin2pnach.load_config(args.config)
    run_generator(ROOT)            # src/ap_locations.h, for pickup.c (when this checkout has it)
    import_patches(config)
    write_patch_list(config)
    compile_patches(config)
    written = {name: Path(bin2pnach.write_pnach(config, name)) for name in config['pnach']}

    if args.install is not None:
        name = args.install or config['install']['pnach']
        if name not in written:
            sys.exit(f"--install: no [pnach.{name}] in {args.config} (have: {', '.join(written)})")
        install(config, name, written[name])


if __name__ == '__main__':
    main()
