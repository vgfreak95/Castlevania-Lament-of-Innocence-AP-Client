/* Castlevania: Lament of Innocence (SLUS-20733) - game symbols used by the
 * debug menu. Addresses are defined in game.ld; everything here was identified
 * in Ghidra. */
#ifndef GAME_H
#define GAME_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

/* ---- player status struct (g_PlayerStatus @ 0xB64800, 0x3C0 bytes) ---- */
#define PLAYER_STATUS ((volatile u8 *)0x00B64800)
#define PS_F32(off) (*(volatile float *)(PLAYER_STATUS + (off)))
#define PS_S32(off) (*(volatile int *)(PLAYER_STATUS + (off)))

#define PS_MAX_HP PS_F32(0x000)
#define PS_MAX_HEARTS PS_F32(0x004)
#define PS_HEARTS PS_F32(0x008) /* mirrored to 0x2EC by AddHearts */
#define PS_GOLD PS_S32(0x020)
#define PS_SUBWEAPON PS_S32(0x02C) /* 0xAA-0xAF */
#define PS_ORB PS_S32(0x030)       /* 0x7F-...  */
#define PS_MAX_MP PS_S32(0x044)
#define PS_MP PS_S32(0x048)
#define PS_RELIC PS_S32(0x04C) /* 0x86-0x8F */
#define PS_HP PS_F32(0x2E8)
#define PS_ATTACK PS_F32(0x394)    /* attack damage modifier, worked out from ATK (23 ATK -> 36) */
#define PS_DEF_REDUCE PS_F32(0x3A0) /* damage reduction %, worked out from DEF */

/* ---- controller, port 0 (active-high, idle = 0) ----
 * Pad struct @ 0xA097C0 (0x120 per port), filled by FUN_00415f30 each frame:
 * +2 held, +4 pressed this frame, +6 released this frame, +8 auto-repeat. */
#define PAD0_STRUCT ((u8 *)0x00A097C0)
#define PAD0_HELD (*(volatile u16 *)0x00A097C2)
#define STICK_CENTRE 0x80

/* Fills one pad struct from libpad data; called once per port per frame from
 * FUN_00416560 (jal @ 0x4165D0). state 5/7 = connected (2/4 = connected,
 * digital only). */
void PadUpdate(u8 *pad, int state, unsigned int buttons, int stick0, int stick1,
               int stick2, int stick3);

/* The game keeps libpad's two button bytes swapped, so the D-pad is in the top
 * nibble (confirmed: FUN_00415f30 cancels 0xA000 = Left+Right and 0x5000 =
 * Down+Up; L3+R3 read 0x0600). */
#define BTN_L2 0x0001
#define BTN_R2 0x0002
#define BTN_L1 0x0004
#define BTN_R1 0x0008
#define BTN_TRIANGLE 0x0010
#define BTN_CIRCLE 0x0020
#define BTN_CROSS 0x0040
#define BTN_SQUARE 0x0080
#define BTN_SELECT 0x0100
#define BTN_L3 0x0200
#define BTN_R3 0x0400
#define BTN_START 0x0800
#define BTN_UP 0x1000
#define BTN_RIGHT 0x2000
#define BTN_DOWN 0x4000
#define BTN_LEFT 0x8000

/* ---- game functions ---- */
void HUD_UpdateVisibility(void); /* the call our hook replaces */
/* 0x452B28: last call of GameplayFrame case 0 (@ 0x439F08); runs on paused frames too */
void FrameEnd(void);
int GamePrintf(const char *fmt,
               ...); /* printf @ 0x400930: retail stub, routed to the EE console
                        by the "Debug printf" pnach */
void AddHP(float amount);        /* clamps 0..MaxHP */
void AddMaxHP(float amount);     /* clamps 10..999, also heals on increase */
void AddHearts(float amount);    /* clamps 0..MaxHearts */
void AddMaxHearts(float amount); /* clamps 10..999, also refills on increase */
void AddGold(int amount);        /* clamps ..999999 */
void AddMP(int amount);          /* clamps 0..MaxMP */
void AddMaxMP(int amount);       /* clamps 10..999 */
int GetMaxMP(void);

/* Item text. Strings live in the loaded text bank and may contain ^ colour codes. */
char *GetText(int text_id);            /* text bank lookup by number */
char *Item_GetNameText(int id);        /* 0x44BA30 */
char *Item_GetDescText(int id);        /* 0x44BA50: text ID from Item_GetInfo(id)+0x0C */
char *Item_GetDescTextSafe(int id);    /* 0x6B77B8: 0 for empty slots (0, 0xFFFFFE, 0xFFFFFF) */

/* Applies a touched pickup object (item ID at obj+0x104). 1 = taken, 0 = stays on the floor. */
int Item_OnPickup(u8 *obj);            /* 0x447078 */

/* ---- objects (actors) ----
 * g_ObjManager @ 0x7386F0 -> manager; *(manager+0) is the list head. Objects are 0x240-byte pool
 * slots; the first 0x220 bytes are laid out per type, the tail is shared (Obj_UpdateAll 0x442730). */
#define OBJ_MANAGER  (*(u8 *volatile *)0x007386F0)
#define OBJ_UPDATE   0x220   /* update function; identifies the object type */
#define OBJ_NEXT     0x230   /* next object, 0 = end */
#define OBJ_FLAGS    0x23C   /* u16 */

/* ---- item pickup objects (update function ItemObj_Update) ----
 * ItemObj_Update computes the squared distance from Leon (his position raised 240 units) to the
 * item's centre (position raised by +0x150 * +0x124) into +0x134; ItemObj_CheckTouch picks the
 * item up when it is below +0x148. ItemObj_Spawn sets +0x144 = 270 and +0x148 = 270^2. */
#define ITEMOBJ_UPDATE_FN  0x00447A98
#define ITEMOBJ_POS        0x000   /* float[4] */
#define ITEMOBJ_ID         0x104   /* int: item ID */
#define ITEMOBJ_HEIGHT_A   0x124   /* float: centre height = A * B */
#define ITEMOBJ_DIST2      0x134   /* float: squared distance to Leon's centre */
#define ITEMOBJ_RADIUS2    0x148   /* float: squared pickup radius */
#define ITEMOBJ_HEIGHT_B   0x150   /* float */
#define ITEMOBJ_OBJFLAGS   0x23C   /* u16: object flags (Obj_UpdateAll) */
/* ItemObj_CheckTouch (0x447960) also shows the item's name in the bottom left (0x447000) while
 * Leon's centre is within this range, a fixed 480^2 compare against +0x134 */
#define ITEM_TEXT_RANGE    480.0f
#define ITEM_PICKUP_RADIUS 270.0f  /* ItemObj_Spawn's default (+0x144) */

/* Inventory item preview (InvMenu_ModelPreview? 0x6CEC18): the hovered item is spawned with
 * ItemObj_Spawn at g_InvPreviewSpawnPos[page] (0x799720, 0x30 bytes each, position first) and only
 * then moved in front of the camera. It is a real pickup and item objects update while paused, so
 * if Leon's centre is within the pickup radius of that world position, every hover gives +1 of the
 * item (the stage 7 room 2 dupe). Entry 0 is the origin; 1-5 are about (-200, -55, 1000). */
#define INV_PREVIEW_SPAWN       ((volatile float *)0x00799720)
#define INV_PREVIEW_STRIDE      12    /* floats */
#define INV_PREVIEW_FIRST_PAGE  1
#define INV_PREVIEW_PAGES       5

/* 0x4613D0: tests flag bits `mask` of player `player` (player struct +0xC30, via 0x46D9C0).
 * ItemObj_CheckTouch calls it as (0, 1) right before a pickup (jal @ 0x4479C0) and leaves the
 * item on the floor when it returns nonzero; that call is the only way into a pickup. */
int Player_TestFlag(int player, int mask);
/* 0x461398: sets (on = 1) or clears flag bits `mask` of player `player` (struct +0xC30, via
 * 0x46D988). The damage handler (0x467178) ends with: HP < 1 (after the revive relic, equip item
 * 0x1A, had its chance) -> Player_SetFlag(player, PLAYER_FLAG_DEAD, 1), which starts the death. */
void Player_SetFlag(int player, int mask, int on);
#define PLAYER_FLAG_DEAD 0x1
#define OBJFLAG_PERSISTENT 0x400   /* set by PlacedItem_Spawn on items with a collected flag */
#define ITEM_ID_NO_EFFECT  0xA6    /* Bloody Skull: Item_OnPickup has no case for it, gives nothing */

/* Box objects (update function 0x454518): min/max corners at +0x00/+0x10, three per room in the
 * rooms checked. Possibly door/exit triggers; unconfirmed. */
#define BOXOBJ_UPDATE_FN   0x00454518
#define BOXOBJ_MIN         0x000   /* float[4] */
#define BOXOBJ_MAX         0x010   /* float[4] */

/* ---- player ----
 * Player structs @ 0xB632C0, 0x1500 bytes each; position at +0x170 (GetPlayerPos 0x460CE8).
 * World Y points down: up is negative. */
#define PLAYER_POS ((volatile float *)0x00B63430)
#define PLAYER_CENTRE_RAISE 240.0f   /* ItemObj_Update measures item distance from here */

/* 0x460C90: sets player `player`'s position (+0x170 and +0x180) and moves the model root
 * (0x440DD8 -> 0x42A338). `pos` is read with lq: 16-byte aligned float[4], w = 1. The players'
 * update (0x460590) runs before HUD_UpdateVisibility in GameplayFrame case 0, so a position set
 * from menu_hook overrides that frame's gravity and collision push-out. */
void SetPlayerPos(int player, const float *pos);

/* 0x5DBDC8: ray cast against the level collision (Cl_RayCastGrid 0x5DDAB8 on g_ClWorld).
 * ray: start (x, y, z, 1) then the segment (dx, dy, dz, 0), end = start + segment; 16-byte
 * aligned (lqc2). mask: polygon kinds, low byte (3 = the kinds the player's checks use).
 * Returns nonzero on a hit: *poly = the nearest polygon, hit = its point (w = fraction along the
 * segment, 16-byte aligned). The polygon's plane (nx, ny, nz, d) is at *(float **)(poly + 0xC);
 * floors face up, ny = -1 (the player code checks for exactly -1.0). */
int Cl_RayCast(const float *ray, u8 **poly, float *hit, int mask);
#define CL_POLY_PLANE  0x0C
#define CL_MASK_PLAYER 3

/* ---- camera ----
 * Camera @ 0x734E00. 0x712310 rebuilds its matrices when +0x512 is set: +0x100 view->screen
 * (sceVu0ViewScreenMatrix 0x6E7090, centre 2048,2048), +0x200 world->view, +0x280 = +0x100 * +0x200.
 * Matrices are 4 float columns: out[i] = m[i]*x + m[4+i]*y + m[8+i]*z + m[12+i]*w. */
float *Camera_GetWorldScreen(void);   /* 0x7121D0: &camera+0x280, rebuilt first if stale */
float *Camera_GetWorldView(void);     /* 0x712208: &camera+0x200, rotation rows orthonormal */
#define GS_SCREEN_CENTRE 2048.0f

/* 0x44AEB0: creates an item pickup object; returns it or 0 */
u8 *ItemObj_Spawn(int id, int group, int type, int sel, int pickup_cb, void *pos, void *rot);

/* ---- placed floor items (PlacedItem_Spawn? 0x56ACF8 / PlacedItem_Update 0x56A7F0) ----
 * The owning actor: +0x0 item object, +0x8 item ID, +0xC kind (0, 1, 6 open the "Obtained"
 * window after pickup), +0x10 persistent, +0x14 collected-flag index (0-63 per room). */
#define PLACED_OBJ    0x00
#define PLACED_ID     0x08
#define PLACED_KIND   0x0C
#define PLACED_INDEX  0x14
#define PLACED_KIND_NO_WINDOW 2    /* PlacedItem_Update just deletes the actor for this kind */

/* 0x6B3B80: nonzero when collected flag `index` of room `room_key` is set (PlacedItem_Spawn skips
 * the item then; jal @ 0x56AE04) */
int GetRoomItemFlag(int room_key, int index);
/* 0x44B740: item ID -> info record (+0x0C desc text, +0x3C effect amount), 0 for IDs >= 0xB0 */
void *Item_GetInfo(int id);
/* 0x43F270: one frame of the ending sequence (GameStateManager state 0xD, jal @ 0x43A958);
 * nonzero when it is over */
int Ending_Update(void);

int GetCurrentStage(void);             /* 0x453158: u16 @ 0x738E94 */
int GetCurrentRoom(void);              /* 0x453178: u16 @ 0x738E96 */
int GetRoomKey(int stage, int room);   /* 0x4531A8: global room number */

/* ---- rooms ----
 * Current room state @ 0x738E94: u16 stage, room, object list, entrance (the spawn point used to
 * enter). "Next" room @ 0x738E9C, same layout, copied to the current one when the new room loads. */
#define CUR_STAGE    (*(volatile u16 *)0x00738E94)
#define CUR_ROOM     (*(volatile u16 *)0x00738E96)
#define CUR_OBJLIST  (*(volatile u16 *)0x00738E98)  /* which ROOMDATA object list; doors use 0 */
#define CUR_ENTRANCE (*(volatile u16 *)0x00738E9A)

/* Room table, loaded from disc file 1021 at boot (0x452F50); pointer @ 0x738E90, 0 before that.
 * Retail: 11 stages, 416 rooms (74 55 57 65 10 49 6 10 58 1 31). */
typedef struct {
    short stage_count;   /* +0x00 */
    short unknown;       /* +0x02: 1 */
    u8 ***rooms;         /* +0x04: per-room data pointers, [stage][room] (0x453A58) */
    int *room_count;     /* +0x08: per stage */
    int *first_key;      /* +0x0C: per stage; GetRoomKey = first_key[stage] + room */
} RoomTable;
#define ROOM_TABLE (*(RoomTable *volatile *)0x00738E90)

/* The loaded room's data, 0 while none is loaded (0x452FA0 and 0x453718 check). At +4: a table of
 * object lists, list n at [1 + n] (n = CUR_OBJLIST). A list is an int count, then 128-byte object
 * records from +0x10, spawned by type (+0x58) on room load. The entrance is an index into this
 * list: the player spawns at that object (0x453718), with no range check. */
#define ROOMDATA (*(u8 *volatile *)0x00B5F4E0)
#define ROOMDATA_OBJLISTS 0x04
#define OBJLIST_COUNT     0x00
/* Door records (object list 0; BoxObj_Update 0x454518 reads them): float x, y, z at +0x00, yaw at
 * +0x14, size (thickness, height, width) at +0x20, destination at +0x50: s16 stage, room,
 * object list, entrance (-1 = none). */
#define DOOR_DEST_STAGE   0x50
#define DOOR_DEST_ROOM    0x52

/* 0x4539F0: start a transition to (stage, room), arriving at `entrance` of object list `objlist`.
 * Does nothing unless stage < stage_count and room < room_count[stage]; the entrance is not checked.
 * Door transitions call it as (stage, room, 0, entrance). */
void RequestRoomChange(int stage, int room, int objlist, int entrance);

/* sub-weapons: Item_OnPickup equips a picked-up one with SetSubWeapon(id, GetActiveOrb()) */
void SetSubWeapon(int id, int orb);    /* 0x468A70 */
int GetActiveOrb(void);                /* 0x468AF8 */

/* 0x4384C0: nonzero while the world is frozen (message box, events); GameplayFrame then skips
 * everything up to 0x439EF0 */
int IsWorldFrozen(void);

/* the game's sprintf @ 0x410410 (named to avoid clashing with the C library builtin) */
int GameSprintf(char *dst, const char *fmt, ...);
/* Both only read the arguments passed in registers (a0-a7) correctly: at most 7 values after the
 * format for GamePrintf, 6 for GameSprintf. Later ones come out as garbage, so build longer lines
 * in pieces. */

/* ---- message box (the "Obtained" window), one global box ----
 * Usage copied from PlacedItem_Update / PlacedItem_MsgBoxTick: freeze the world, MsgBox_Open,
 * then every frame MsgBox_Update + MsgBox_Draw until Update returns nonzero (player confirmed),
 * then MsgBox_Close and unfreeze. Text: \n line breaks, ^Crrggbbaa colour, ^c colour reset. */
#define MSGBOX_STYLE_OBTAINED 0x520120
#define MSGBOX_OPEN_FLAG      0x08       /* int at box+8: nonzero while a box is shown */
u8 *MsgBox_Get(void);                                     /* 0x6B6170: &box @ 0xB8EDD8 */
void MsgBox_Open(u32 style, const char *text, int mode);  /* 0x6B62B0 */
int MsgBox_Update(u8 *box);                               /* 0x6B4590: nonzero = confirmed */
void MsgBox_Draw(u8 *box);                                /* 0x6B49C0 */
void MsgBox_Close(u8 *box);                               /* 0x6B4A08 */
void World_Freeze(int arg);           /* 0x438908: freeze enemies/objects (game passes 0) */
void World_Unfreeze(void);            /* 0x438938 */
void World_SetPausedBit(int on);      /* 0x438620: bit 0 of 0xB36750 */
void Sound_StopLoops(void);           /* 0x452388 */
void Pad_StopVibration(int a, int port); /* 0x403E48: game calls (0, -1); unconfirmed */

/* Text renderer @ 0x6B7290 (64 callers). Lays out the string, then queues glyph
 * sprites, so it can be called from the frame update. Supports the game's ^Wnn
 * colour codes. x/y are relative to the screen centre (negative y = up). colour
 * is ABGR, 0x80 = full. */
typedef struct {
  int font;   /* 8 in the game's menus */
  u32 colour; /* unused by the draw call itself; kept as in the game's template
               */
  int flags;
  int scale_x; /* 0x100 = 1.0 */
  int scale_y; /* 0x100 = 1.0 */
  int reserved;
} TextStyle;
void DrawText(const char *text, const TextStyle *style, int x, int y, int layer,
              u32 colour);

#define RGBA(r, g, b, a)                                                       \
  ((u32)(r) | ((u32)(g) << 8) | ((u32)(b) << 16) | ((u32)(a) << 24))

/* 0x460828: a player update step, void(void); GameplayFrame case 0 calls it (jal @ 0x439EC8)
 * before HUD_UpdateVisibility, only on frames where the world isn't frozen */
void Player_UpdateStep(void);
/* 0x442730: updates every object; GameplayFrame case 0 calls it at 0x439EE8 and 0x439F00, the
 * second after the frozen-frame skip, so it runs on frozen frames too */
void Obj_UpdateAll(void);

/* ---- 2D primitives: per-frame GS packet objects ----
 * Usage copied from the screen fade (0x43F390): Prim_Alloc, GS register list (GsRegs_Init/Set),
 * Prim_Init, Prim_SetRegs, Prim_SetFlags, Prim_SetVertexCount, Prim_SetColour, fill the vertices
 * at obj + 0x50, then submit. The GIF tag is at obj + 0x30 (PRIM in bits 47-57), RGBAQ at +0x40
 * (four ints, 0x80 = full). Type 4: vertex count 2 = sprite (UV, XYZ2 per vertex, 0x20 bytes),
 * count 0 = 4-vertex triangle strip (same layout). XY are GS 12.4 fixed point, screen centre at
 * 2048: (screen + 2048) * 16. */
u8 *Prim_Alloc(int size);                         /* 0x457590: per-frame scratch, 0 when full */
void Prim_Init(u8 *obj, int type);                /* 0x457DB8 */
void Prim_SetFlags(u8 *obj, int a, int fge, int abe, int fix); /* 0x457AB8: game passes (1,0,abe,0) */
void Prim_SetVertexCount(u8 *obj, int count);     /* 0x457CD0: type 4 only */
void Prim_SetColour(u8 *obj, const int *rgba);    /* 0x457A00 */
void Prim_SetRegs(u8 *obj, u8 *regs);             /* 0x457F78 */
void GsRegs_Init(u8 *regs);                       /* 0x4575E0: A+D list, 5 slots, 0x60 bytes */
/* 0x457630: the game takes a 64-bit value in a2 (stored with sd); declared u32 so it is passed in
 * one register, which is enough for values below 0x80000000 */
void GsRegs_Set(u8 *regs, int reg, u32 value);
void Prim_SubmitLayer(u8 *obj, int layer);        /* 0x459E20: layer < 0x65, DrawText's layer */
#define PRIM_TAG        0x30
#define PRIM_VERTS      0x50
#define PRIM_TME_BYTE   0x36       /* GIF tag byte holding PRIM bit 4 (texture on) */
#define PRIM_TME_BIT    0x08
#define GS_REG_TEST_1   0x47
#define GS_REG_ALPHA_1  0x42

/* ---- area map (the pause map's data, loaded at stage load and kept) ----
 * File pointer @ 0xB90974 (disc file id @ 0xB90970): +0 relocated flag (1), +4 piece count,
 * +0x30 piece pointers. Piece (0x60 bytes): +0 stage, +1 room, +2 floor, +8 u16 flags,
 * +0xB size in squares, +0x10 u16 part counts per kind, +0x1A u8[4] fill parts, +0x1E u8[4]
 * outline parts, +0x40 float x, y, z, yaw, +0x50 float scale x, y, z.
 * The pause map model follows the pieces (16-byte aligned, magic 0xFFFFxxxx): +0x20 mesh count,
 * +0x24 offset of the first mesh. Meshes are back to back, u32 byte size first, byte +0x43 =
 * part index; their VIF UNPACK V3-32 blocks (cmd byte 0x68, count = byte 2) hold int32 vertices
 * in area map space: map x = vx / 16, map z = -vz / 16. Leon -> map (pause map marker 0x6C3EB8):
 * piece.pos + piece.scale * RotY(piece.yaw) * 0.1 * (x, 0, z). */
#define MAP_FILE (*(u8 *volatile *)0x00B90974)
u8 *Map_GetCurrentPiece(void);    /* 0x6C1048: current room's piece for Leon's floor, or 0 */
#define PIECE_ROOM     0x01
#define PIECE_FLOOR    0x02
#define PIECE_FLAGS    0x08        /* u16 */
#define PIECE_FLAG_SAVE 0x0002     /* the pause map draws the outline red (0x6C20B8, colours @ 0x7984A0) */
#define PIECE_SQUARES  0x0B
#define PIECE_COUNTS   0x10
#define PIECE_FILL     0x1A
#define PIECE_OUTLINE  0x1E
#define PIECE_POS      0x40        /* float x, y, z, yaw */
#define PIECE_SCALE    0x50
#define MODEL_MESH_COUNT 0x20
#define MODEL_MESH_OFS   0x24
#define MESH_PART        0x43
#define VIF_UNPACK_V3_32 0x68

/* room state table: 12 bytes per room key, bit 0 of the first word = visited */
#define ROOM_STATE (*(u32 *volatile *)0x00797D40)
#define ROOM_STATE_COUNT (*(volatile int *)0x00797D44)

#endif
