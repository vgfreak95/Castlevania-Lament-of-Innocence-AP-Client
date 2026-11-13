/* Link a patch into free EE RAM and bind game symbols to their addresses.
 * PATCH_BASE comes from build.sh (-Wl,--defsym). Code cave: 0x96000-0xFFFFF was unused at
 * runtime (BIOS loader leftovers end at 0x96000); each patch gets its own block in it. */
OUTPUT_ARCH(mips)
ENTRY(PATCH_BASE)

/* game functions: game_symbols.ld (shared with the debug tools) */
INCLUDE game_symbols.ld

SECTIONS
{
    . = PATCH_BASE;
    .text   : { KEEP(*(.text.menu_hook)) *(.text .text.*) }
    .rodata : {
        /* menu.h SUBMENU(): one pointer per submenu, in order of the number in the section name */
        . = ALIGN(4);
        __submenus_start = .;
        KEEP(*(SORT_BY_NAME(.submenus.*)))
        __submenus_end = .;
        *(.rodata .rodata.* .rodata1) *(.data .data.* .sdata .sdata.*)
    }
    /* NOBITS: not part of the binary, so the pnach never resets the menu state */
    .bss (NOLOAD) : ALIGN(16) { *(.sbss .sbss.* .bss .bss.* COMMON) }
    /DISCARD/ : { *(.MIPS.abiflags) *(.reginfo) *(.comment) *(.pdr) *(.gnu.attributes) *(.mdebug*) }
}
