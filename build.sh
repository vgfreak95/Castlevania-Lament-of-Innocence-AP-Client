#!/bin/sh
# Compiles the patches. Run by tools/build.py, inside the ps2dev/ps2dev container or with the PS2
# toolchain on PATH; the patch list comes from config.toml via build/patches.txt.
set -e

CC=mips64r5900el-ps2-elf-gcc
mkdir -p build

# build_patch <name> <base address> <cflags and sources...>: -> build/<name>.{elf,bin,map,lst}
build_patch() {
    name=$1
    base=$2
    shift 2

    # 1. compile + link into an ELF, placed at the patch's base address
    $CC -O2 -G0 -mno-abicalls -fno-pic -ffreestanding -fno-builtin -nostdlib \
        -Wall -Wextra -Wno-unused-parameter \
        -T game.ld -Wl,--defsym=PATCH_BASE=$base -Wl,--no-warn-rwx-segments \
        -o build/$name.elf "$@"

    # 2. <name>.bin: the raw bytes
    mips64r5900el-ps2-elf-objcopy -O binary build/$name.elf build/$name.bin

    # 3. <name>.map: the symbol list
    mips64r5900el-ps2-elf-nm -n build/$name.elf > build/$name.map
    mips64r5900el-ps2-elf-objdump -d build/$name.elf > build/$name.lst
    mips64r5900el-ps2-elf-size -A build/$name.elf
}

# one patch per line: <name> <base address> <cflags and sources...>
while read -r name base args; do
    build_patch $name $base $args
done < build/patches.txt
