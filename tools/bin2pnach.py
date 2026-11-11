"""
Turn build/<name>.bin files into PCSX2 pnaches: one 32-bit write per word plus the hook patches.
Each patch becomes its own [group], so it can be switched on and off in PCSX2.
The patches and which pnach they go in come from config.toml.

usage: py -3 tools/bin2pnach.py [--config config.toml] [pnach ...]   (default: every [pnach.*])
"""
import argparse
import os
import re
import struct
import tomllib

PRINTF_SECTION = """[Debug printf]
author={author}
description=Redirect the stubbed printf at 0x400930 to the PCSX2 EE console
patch=1,EE,00400930,word,24030075
patch=1,EE,00400934,word,0000000C
patch=1,EE,00400938,word,03E00008
patch=1,EE,0040093C,word,00000000
"""


def load_config(path):
    with open(path, 'rb') as f:
        return tomllib.load(f)


def read_map(path):
    syms = {}
    # ([0-9a-fA-F]{8}): the 8 hex digits of the address (group 1)
    # \s+\w\s+: spaces, the one-letter symbol type (T = code, b = bss, A = absolute), spaces
    # (\S+): the name (group 2)
    for line in open(path):
        m = re.match(r'([0-9a-fA-F]{8})\s+\w\s+(\S+)', line)
        if m:
            # for example: syms['pad_hook'] = 0xF0758
            syms[m.group(2)] = int(m.group(1), 16)
    return syms


def patch_section(name, patch, build_dir, author):
    syms = read_map(os.path.join(build_dir, name + '.map'))

    # where the patch's code starts (the patch's base in config.toml)
    base = syms['PATCH_BASE']

    code = open(os.path.join(build_dir, name + '.bin'), 'rb').read()
    code += b'\0' * (-len(code) % 4)  # pad to a multiple of 4 bytes (-len % 4 = bytes missing)

    # For example, the bytes E0 FF BD 27 become 0x27BDFFE0
    words = struct.unpack(f'<{len(code) // 4}I', code)
    hooks = []
    for h in patch['hooks']:
        if h['function'] not in syms:
            raise SystemExit(f"{name}: hook function {h['function']} not found in {name}.map")
        hooks.append((h['site'], h['original'], 0x0C000000 | (syms[h['function']] >> 2), h['function']))

    lines = [
        f"[{patch['title']}]",
        f'author={author}',
        f"description={patch['description']}",
        f'// {len(code)} bytes at {base:#010x}',
    ]
    lines += [f'// hook {site:#010x}: {orig:08X} -> {jal:08X} ({fn})' for site, orig, jal, fn in hooks]
    lines += [f'patch=1,EE,{base + 4 * i:08X},word,{w:08X}' for i, w in enumerate(words)]
    lines += [f'patch=1,EE,{site:08X},word,{jal:08X}' for site, _, jal, _ in hooks]

    print(f"{patch['title']}: {len(words)} words at {base:#x}, " +
          ', '.join(f'{fn}={syms[fn]:#x}' for _, _, _, fn in hooks))
    return '\n'.join(lines) + '\n'


def write_pnach(config, pnach_name, build_dir='build'):
    """Write [pnach.<pnach_name>] to <dir>/<crc>.pnach and return its path."""
    pnach = config['pnach'][pnach_name]
    author = config['build']['author']
    sections = [PRINTF_SECTION.format(author=author)]
    for name in pnach['patches']:
        sections.append(patch_section(name, config['patch'][name], build_dir, author))

    os.makedirs(pnach['dir'], exist_ok=True)
    out = os.path.join(pnach['dir'], config['game']['crc'] + '.pnach')
    with open(out, 'w', newline='\n') as f:
        f.write('\n'.join(sections))
    print(f'{out} written')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='config.toml')
    ap.add_argument('pnach', nargs='*', help='[pnach.*] names to write (default: all)')
    args = ap.parse_args()

    config = load_config(args.config)
    for name in args.pnach or config['pnach']:
        write_pnach(config, name)


if __name__ == '__main__':
    main()
