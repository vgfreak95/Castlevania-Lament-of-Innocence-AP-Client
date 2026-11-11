/* Link a patch into free EE RAM and bind game symbols to their addresses.
 * PATCH_BASE comes from build.sh (-Wl,--defsym). Code cave: 0x96000-0xFFFFF was unused at
 * runtime (BIOS loader leftovers end at 0x96000); each patch gets its own block in it. */
OUTPUT_ARCH(mips)
ENTRY(PATCH_BASE)

/* game functions (SLUS_207.33, identified in Ghidra) */
GamePrintf           = 0x00400930;
HUD_UpdateVisibility = 0x00433AE8;
FrameEnd             = 0x00452B28;
AddHP                = 0x00468558;
AddMaxHP             = 0x004685E8;
AddHearts            = 0x004686A8;
AddMaxHearts         = 0x00468758;
AddGold              = 0x00468818;
GetMaxMP             = 0x00468BF0;
AddMaxMP             = 0x00468C10;
AddMP                = 0x00468CD0;
DrawText             = 0x006B7290;
PadUpdate            = 0x00416438;
GetText              = 0x004552C0;
Item_GetNameText     = 0x0044BA30;
Item_GetDescText     = 0x0044BA50;
Item_GetDescTextSafe = 0x006B77B8;
Item_OnPickup        = 0x00447078;
ItemObj_Spawn        = 0x0044AEB0;
GetCurrentStage      = 0x00453158;
GetCurrentRoom       = 0x00453178;
GetRoomKey           = 0x004531A8;
RequestRoomChange    = 0x004539F0;
SetSubWeapon         = 0x00468A70;
GetActiveOrb         = 0x00468AF8;
IsWorldFrozen        = 0x004384C0;
GameSprintf          = 0x00410410;
Camera_GetWorldScreen = 0x007121D0;
Player_TestFlag      = 0x004613D0;
SetPlayerPos         = 0x00460C90;
Camera_GetWorldView  = 0x00712208;
Cl_RayCast           = 0x005DBDC8;
MsgBox_Get           = 0x006B6170;
MsgBox_Open          = 0x006B62B0;
MsgBox_Update        = 0x006B4590;
MsgBox_Draw          = 0x006B49C0;
MsgBox_Close         = 0x006B4A08;
World_Freeze         = 0x00438908;
World_Unfreeze       = 0x00438938;
World_SetPausedBit   = 0x00438620;
Sound_StopLoops      = 0x00452388;
Pad_StopVibration    = 0x00403E48;
GetRoomItemFlag      = 0x006B3B80;
Item_GetInfo         = 0x0044B740;
Ending_Update        = 0x0043F270;

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
