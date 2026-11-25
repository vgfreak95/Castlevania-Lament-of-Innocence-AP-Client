/* Custom ticket (see ticket.h).
 *
 * Item: usable items (category 4, IDs 0x2A-0x54) have 0x50-byte info records from 0x73AC08, by
 * ID - 0x2A (Item_GetInfo). +0x00/+0x04 name text (+0x04 in game mode 2), +0x08/+0x18 and
 * +0x0C/+0x1C description texts, +0x14 description in game mode 2, +0x24 model, +0x28 palette
 * (TEX0 CSA, set on the model by 0x45AA30 -> 0x4577D8), +0x3C use type (byte; 7 = ticket).
 * 0x4D-0x54 are blank records. ticket_frame copies the Memorial Ticket's record into 0x4D every
 * frame (a console reset reloads the game's data) with custom text IDs, palette 2 (a red one
 * written into the ticket model's CLUT), a red icon (see "red icon" below), a shop price and a max
 * stack of 1 (ticket.h). It is never placed by the apworld: Rinaldo's shop is the only source.
 *
 * Texts: every item name/description lookup ends in a tail call "j GetText" (Item_GetNameText
 * 0x44BA48, Item_GetDescText 0x44BAB4, the short description 0x44BB74). Those three j are
 * replaced (config.toml) by item_text_hook, which answers the custom text IDs and passes the rest
 * on to GetText (itself taken over by the Archipelago Pickups patch for the area keys, which
 * still works: this calls it at its entry).
 *
 * Use: the item ring (0x46DDA0) starts a usable item with ItemUse_Spawn(player, id) (0x471A50),
 * which creates an effect object running the update for the record's use type (table @ 0x7AACB0;
 * tickets: 0x473C88). For the custom ticket, ticket_use_hook opens the save room picker instead
 * (see "use" below); a picked room starts the effect as a Memorial Ticket (it only plays the
 * ticket effect for IDs 0x31/0x32) and its object is remembered. When the effect ends (state 3)
 * the update warps (RequestRoomChange), calls 0x453118(0) and removes one ticket
 * (Inv_RemoveItem(obj id, 1)). The warp and the removal are hooked with the object (s2) passed
 * along: for the custom ticket's object the warp goes to the picked save room and nothing is
 * removed (the custom ticket is reusable).
 *
 * Hooks (config.toml, Minimap patch): j item_text_hook @ 0x44BA48 / 0x44BAB4 / 0x44BB74, jal
 * ticket_use_hook @ 0x46E0F8, ticket_warp_stub @ 0x47436C / 0x4743A4, ticket_remove_stub @
 * 0x4743BC, ticket_frame_hook @ 0x439EF0, text_code_hook @ 0x445F00 / 0x443C9C / 0x444D7C /
 * 0x4451E4. */
#include "ticket.h"
#include "apmenu.h"
#include "savewarps.h"
#include "apshop.h"

#define USABLE_FIRST       0x2A
#define USABLE_INFO(id)    ((u32 *)(0x0073AC08 + ((id) - USABLE_FIRST) * 0x50))
#define USABLE_INFO_WORDS  (0x50 / 4)
#define INFO_NAME          0       /* words */
#define INFO_NAME_ALT      1
#define INFO_DESC_SHORT    2
#define INFO_DESC          3
#define INFO_DESC_ALT      5
#define INFO_DESC_SHORT2   6
#define INFO_DESC2         7
#define INFO_PALETTE       10
#define INFO_MAX_STACK     13      /* +0x34: the shop's cap (0x6B7DD8) */
#define INFO_PRICES        17      /* +0x44: s16 buy price, s16 sell price */

/* custom text IDs, far past the bank's 1111 entries and clear of the area keys' 0x7F00 */
#define TEXT_NAME 0x7E00
#define TEXT_DESC 0x7E01

static const char ticket_name[] = "Savewarp Ticket";
/* one line is too long for the shop's description box: break after "one" so nothing is cut off */
static const char ticket_desc[] = "Use in a save room to warp to another one\nyou have visited.";

/* state lives in .bss, which the pnach never writes */
static u8 *ticket_obj;          /* effect object of the custom ticket in use, 0 = none */

/* game functions only this file uses (addresses in game.ld) */
u8 *ItemUse_Spawn(int player, int id);         /* 0x471A50 */
int Inv_RemoveItem(int id, int count);         /* 0x4690E0: returns the part it couldn't take */
u8 *Model_GetData(int model);                  /* 0x446C48: model ID -> loaded model data */
u8 *Tex_Find(int tex_id);                      /* 0x417950: texture/CLUT ID -> descriptor */
void Clut_Upload(u8 *desc, int slot);          /* 0x418ED8: queues the CLUT's transfer to VRAM */

/* ---- red palette ----
 * Model data (magic 0x2002): +0x08 u16 texture ID, +0x0A u16 CLUT ID, +0x0C u16 palette. Texture
 * descriptors (Tex_Find): +0x12 u16 offset of the pixels from the descriptor, +0x1D PSM, +0x1E
 * width, +0x1F height, +0x24 qword count. The tickets' model (0x30, the Memorial Ticket record's
 * +0x24) has a 4-bit texture and a full 256-entry CT32 CLUT, 16x16, uploaded whole, of which only
 * palettes 0 (Memorial, gold) and 1 (Magical, blue) are filled; the rest is zero (black).
 * In a CSM1 CT32 CLUT, palette n (CSA) is the 8x2 block at x = (n & 1) * 8, y = (n >> 1) * 2, so
 * palette 2 is rows 2-3, columns 0-7. It is made from the Memorial palette: red kept, green and
 * blue set to half the blue, which turns gold into crimson with the same shading.
 * The CLUT goes to VRAM when a model using it is set up and it isn't resident: the CLUT cache
 * (list @ 0xA1E580; node +0x04 next, +0x08 CLUT ID, +0x0C u16 VRAM slot) keeps it there. So the
 * palette is written into the loaded data (a stage load brings a fresh copy, so it is checked every
 * frame) and, if the CLUT is resident at that moment, sent again into the same slot. */
#define MODEL_TICKET_CLUT  0x0A
#define MODEL_MAGIC        0x2002
#define DESC_DATA          0x12
#define DESC_PSM           0x1D
#define DESC_W             0x1E
#define DESC_H             0x1F
#define DESC_QWC           0x24
#define CLUT_W             16
#define CLUT_CACHE         (*(u8 *volatile *)0x00A1E580)
#define CACHE_NEXT         0x04
#define CACHE_ID           0x08
#define CACHE_SLOT         0x0C
#define INFO_MODEL         9       /* word: +0x24 */

static u32 red_of(u32 c)   /* ABGR: R low byte */
{
    u32 r = c & 0xFF, b = (c >> 16) & 0xFF, a = c & 0xFF000000;
    u32 gb = b >> 1;

    return a | gb << 16 | gb << 8 | r;
}

static int clut_slot(int clut_id)
{
    u8 *node;

    for (node = CLUT_CACHE; node; node = *(u8 **)(node + CACHE_NEXT))
        if (*(int *)(node + CACHE_ID) == clut_id)
            return *(u16 *)(node + CACHE_SLOT);
    return -1;
}

/* the CLUT's descriptor, if it is loaded and a 16x16 CT32 CLUT (the layout this was worked out on) */
static u8 *clut_desc(int clut_id)
{
    u8 *desc = Tex_Find(clut_id);

    if (!desc || desc[DESC_PSM] != 0 || desc[DESC_W] != CLUT_W || desc[DESC_H] != CLUT_W
        || *(int *)(desc + DESC_QWC) != CLUT_W * CLUT_W / 4)
        return 0;
    return desc;
}

/* entry i (0-15) of palette csa (0-15) in a 16x16 CSM1 CT32 CLUT */
static u32 *clut_entry(u8 *desc, int csa, int i)
{
    u32 *pix = (u32 *)(desc + *(u16 *)(desc + DESC_DATA));

    return pix + ((csa >> 1) * 2 + (i >> 3)) * CLUT_W + (csa & 1) * 8 + (i & 7);
}

/* Writes the red version of palette src_csa of CLUT src_id into palette dst_csa of CLUT dst_id,
 * and sends dst_id to VRAM again if it is resident and something changed. Leaves it alone unless
 * the target palette is empty or already ours. */
static void paint_red(int src_id, int src_csa, int dst_id, int dst_csa)
{
    u8 *src = clut_desc(src_id), *dst = clut_desc(dst_id);
    int i, changed = 0, slot;

    if (!src || !dst)
        return;
    for (i = 0; i < 16; i++) {
        u32 now = *clut_entry(dst, dst_csa, i);
        if (now != 0 && now != red_of(*clut_entry(src, src_csa, i)))
            return;             /* something else lives there */
    }
    for (i = 0; i < 16; i++) {
        u32 *to = clut_entry(dst, dst_csa, i), c = red_of(*clut_entry(src, src_csa, i));
        if (*to != c) {
            *to = c;
            changed = 1;
        }
    }
    if (changed && (slot = clut_slot(dst_id)) >= 0)
        Clut_Upload(dst, slot);
}

static void paint_model_palette(void)
{
    u8 *model = Model_GetData(USABLE_INFO(TICKET_CLONE_OF)[INFO_MODEL]);
    int clut_id;

    if (!model || *(u16 *)model != MODEL_MAGIC)
        return;
    clut_id = *(u16 *)(model + MODEL_TICKET_CLUT);
    paint_red(clut_id, 0, clut_id, TICKET_PALETTE);   /* Memorial's palette 0 -> palette 2 */
}

/* ---- red icon ----
 * Item icons are text: menus print "^I%02x" with the record's +0x20 (Memorial 0x29, Magical 0x28).
 * The text code parser (0x445528, called from four places: layout, measuring and the two glyph
 * drawers) turns ^Ixx into glyph 0xA000 | xx with palette xx + 0x10 (*glyph, *palette). Palette p
 * is CSA p & 15 of the CLUT whose ID is the u16 at 0x7387A0 + (p >> 4) * 2: 16x16 CT32 CLUTs again.
 * Groups 0-7 (icons up to 0x6F) are full; group 8 (CLUT 0x1B10, loaded with the others) has
 * palettes 0x84-0x8F empty. The ticket's record gets an icon code no real icon uses (ICON_FAKE);
 * text_code_hook turns it into the Memorial icon's glyph with ICON_PALETTE, a red copy of the
 * Memorial icon's palette. */
#define INFO_ICON          8       /* word: +0x20 */
#define ICON_FAKE          0xFF
#define ICON_MEMORIAL      0x29
#define ICON_GLYPH         0xA000
#define ICON_PALETTE_OF(n) ((n) + 0x10)
#define ICON_PALETTE       0x8F
#define TEXT_CLUTS         ((volatile u16 *)0x007387A0)

int Text_ParseCode(int *enc, u8 **str, u32 *glyph, u32 *colour, int *palette, int draw); /* 0x445528 */

/* Replaces the four "jal Text_ParseCode" */
int text_code_hook(int *enc, u8 **str, u32 *glyph, u32 *colour, int *palette, int draw)
{
    int r = Text_ParseCode(enc, str, glyph, colour, palette, draw);

    if (*glyph == (ICON_GLYPH | ICON_FAKE)) {
        *glyph = ICON_GLYPH | ICON_MEMORIAL;
        *palette = ICON_PALETTE;
    }
    return r;
}

static void paint_icon_palette(void)
{
    int src = ICON_PALETTE_OF(ICON_MEMORIAL);

    paint_red(TEXT_CLUTS[src >> 4], src & 15, TEXT_CLUTS[ICON_PALETTE >> 4], ICON_PALETTE & 15);
}

/* ---- item ---- */

/* every frame (from ticket_frame_hook): a console reset reloads the game's data */
static void ticket_frame(void)
{
    const u32 *src = USABLE_INFO(TICKET_CLONE_OF);
    u32 *dst = USABLE_INFO(TICKET_ID);
    int w;

    for (w = 0; w < USABLE_INFO_WORDS; w++)
        dst[w] = src[w];
    dst[INFO_NAME] = dst[INFO_NAME_ALT] = TEXT_NAME;
    dst[INFO_DESC_SHORT] = dst[INFO_DESC] = dst[INFO_DESC_ALT] = TEXT_DESC;
    dst[INFO_DESC_SHORT2] = dst[INFO_DESC2] = TEXT_DESC;
    dst[INFO_PALETTE] = TICKET_PALETTE;
    dst[INFO_ICON] = ICON_FAKE;
    dst[INFO_MAX_STACK] = TICKET_STACK;
    dst[INFO_PRICES] = (TICKET_PRICE & 0xFFFF) | ((u32)(TICKET_SELL_PRICE & 0xFFFF) << 16);
    paint_model_palette();
    paint_icon_palette();
}

/* Replaces the "j GetText" tail calls of the item name/description lookups (a0 = text ID). */
char *item_text_hook(int text_id)
{
    char *shop = shop_text(text_id);   /* Shop Sanity rows (apshop.c) */

    if (shop)
        return shop;
    if (text_id == TEXT_NAME)
        return (char *)ticket_name;
    if (text_id == TEXT_DESC)
        return (char *)ticket_desc;
    return GetText(text_id);
}

/* ---- use: save room picker -> ticket effect -> warp ----
 * The ticket only works in a save room (one of save_rooms[]); anywhere else choosing it does
 * nothing but show a short notice.
 * Choosing the ticket in the item ring (ticket_use_hook) doesn't start anything yet: it asks for
 * the picker, which opens as soon as the ring has closed and the world runs. The picker freezes
 * the world (like the Archipelago Menu) and lists the save rooms Leon has been in. Picking one
 * unfreezes it and starts the ticket effect as a Memorial Ticket (glow, sound, Leon fading out);
 * at its end the effect warps to the picked room instead of the Memorial point, and the ticket is
 * kept. Cancelling the picker does nothing.
 * The picker runs from the jal 0x454FE0 @ 0x439EF0 in GameplayFrame case 0, past the frozen-frame
 * skip, so it runs while the world is frozen. Input comes from the game's pad block, as the
 * Archipelago Menu does. While it is open the world's paused bit is set, so the Archipelago Menu
 * doesn't open over it (apmenu_game_busy).
 * Save rooms: the list in savewarps.h. The warp arrives at entrance 0 of the room's own object
 * list, as its corridor door does, so the exit leads back to that corridor (savewarps.c). */
#define SHOWN_MAX 32    /* >= save_room_count */

enum { PICKER_CLOSED, PICKER_PENDING, PICKER_OPEN };

/* Frames (60 per second) from choosing the ticket in the item ring to the picker opening, so the
 * ring has finished closing first (its close takes about 9 frames, 0.15 s, in 0x46DDA0). After
 * the wait the picker still waits for the world to run (no message box, not frozen). */
#define PICKER_DELAY   30

/* used outside a save room: nothing happens, and this notice shows for NOTICE_FRAMES */
#define NOTICE_FRAMES  120
#define NOTICE_TEXT    "Can only be used in a save room"

#define PICKER_X       (-236)
#define PICKER_Y       (-130)  /* first row; the title is a line above */
#define PICKER_LINE    20
#define PICKER_ROWS    14      /* rows shown at once; longer lists scroll */
#define PICKER_LAYER   1
#define COLOUR_TITLE   RGBA(0x80, 0x30, 0x30, 0x80)
#define COLOUR_ITEM    RGBA(0x70, 0x70, 0x70, 0x80)
#define COLOUR_SEL     RGBA(0x80, 0x80, 0x30, 0x80)
#define COLOUR_HELP    RGBA(0x60, 0x60, 0x60, 0x80)
#define PICKER_OK      BTN_CROSS
#define PICKER_CANCEL  (BTN_TRIANGLE | BTN_CIRCLE)
#define PAD0_PRESSED_GAME (*(volatile u16 *)(PAD0_STRUCT + 4))

static const TextStyle picker_style = {8, 0x80808080, 0, 0x100, 0x100, 0};

/* state lives in .bss, which the pnach never writes */
static int picker;              /* PICKER_* */
static int picker_player;       /* the player who used the ticket */
static int picker_wait;         /* PICKER_PENDING: frames left before it opens */
static int picker_sel, picker_top;
static u8 shown[SHOWN_MAX];     /* save_rooms indexes of the visited ones */
static int shown_count;
static const SaveRoom *dest;    /* where the running custom ticket effect warps */
static int notice_frames;       /* > 0: the "save room only" notice is showing */

void Fn_454FE0(void);           /* 0x454FE0: the call the frame hook replaces */

static void picker_open(void)
{
    int i;

    shown_count = 0;
    for (i = 0; i < save_room_count && shown_count < SHOWN_MAX; i++)
        if (save_room_visited(&save_rooms[i]))
            shown[shown_count++] = i;
    picker_sel = picker_top = 0;
    picker = PICKER_OPEN;
    World_Freeze(0);
    World_SetPausedBit(1);
    GamePrintf("[ticket] picker open, %d save rooms visited\n", shown_count);
}

static void picker_close(void)
{
    picker = PICKER_CLOSED;
    World_Unfreeze();
    World_SetPausedBit(0);
}

/* picked: unfreeze and start the effect; the warp comes at its end */
static void picker_confirm(void)
{
    const SaveRoom *s = &save_rooms[shown[picker_sel]];
    u8 *obj;

    picker_close();
    if (Player_TestFlag(0, PLAYER_FLAG_DEAD))
        return;
    obj = ItemUse_Spawn(picker_player, TICKET_CLONE_OF);
    ticket_obj = obj;
    dest = s;
    GamePrintf("[ticket] warping to %s: Save %d (stage %d room %d), effect %08X\n", s->area,
               s->number, s->stage, s->room, (u32)obj);
}

static void picker_draw(void)
{
    char text[64];
    int rows = shown_count ? shown_count : 1, n, i;

    if (picker_sel < picker_top)
        picker_top = picker_sel;
    if (picker_sel >= picker_top + PICKER_ROWS)
        picker_top = picker_sel - PICKER_ROWS + 1;
    n = rows < PICKER_ROWS ? rows : PICKER_ROWS;

    if (rows > PICKER_ROWS)
        GameSprintf(text, "%s  %d-%d of %d", ticket_name, picker_top + 1, picker_top + n, rows);
    else
        GameSprintf(text, "%s", ticket_name);
    DrawText(text, &picker_style, PICKER_X, PICKER_Y - PICKER_LINE, PICKER_LAYER, COLOUR_TITLE);
    for (i = 0; i < n; i++) {
        int row = picker_top + i;

        if (!shown_count) {
            GameSprintf(text, "  No save rooms visited yet");
        } else {
            const SaveRoom *s = &save_rooms[shown[row]];
            char name[SAVE_LABEL_MAX];

            save_room_label(s, name);
            GameSprintf(text, "%s%s%s", row == picker_sel ? "> " : "  ", name,
                        save_room_here(s) ? " (here)" : "");
        }
        DrawText(text, &picker_style, PICKER_X + 4, PICKER_Y + 4 + i * PICKER_LINE,
                 PICKER_LAYER, shown_count && row == picker_sel ? COLOUR_SEL : COLOUR_ITEM);
    }
    DrawText(shown_count ? "Cross warp  Triangle cancel" : "Triangle back", &picker_style,
             PICKER_X, PICKER_Y + 8 + n * PICKER_LINE, PICKER_LAYER, COLOUR_HELP);
}

static void picker_input(u16 pressed)
{
    if (pressed & PICKER_CANCEL) {
        picker_close();
        GamePrintf("[ticket] picker cancelled\n");
    } else if (!shown_count) {
        return;
    } else if (pressed & BTN_UP) {
        picker_sel = (picker_sel + shown_count - 1) % shown_count;
    } else if (pressed & BTN_DOWN) {
        picker_sel = (picker_sel + 1) % shown_count;
    } else if (pressed & PICKER_OK) {
        picker_confirm();
    }
}

/* the ticket was chosen in the ring: open the picker PICKER_DELAY frames later, once the world
 * runs (ticket_frame_hook runs once per frame, frozen or not) */
static void picker_tick_pending(void)
{
    if (picker != PICKER_PENDING)
        return;
    if (picker_wait > 0)
        picker_wait--;
    else if (!apmenu_game_busy())
        picker_open();
}

/* Replaces "jal 0x454FE0" @ 0x439EF0 in GameplayFrame case 0 (runs on frozen frames too). */
void ticket_frame_hook(void)
{
    Fn_454FE0();
    ticket_frame();
    apshop_frame();          /* Shop Sanity item records (apshop.c) */
    if (notice_frames > 0) {
        notice_frames--;
        if (in_save_room())
            notice_frames = 0;   /* walked into one: the notice no longer applies */
        else
            DrawText(NOTICE_TEXT, &picker_style, PICKER_X, PICKER_Y - PICKER_LINE, PICKER_LAYER,
                     COLOUR_TITLE);
    }
    picker_tick_pending();
    if (picker != PICKER_OPEN)
        return;
    if (PAD0_PRESSED_GAME)
        picker_input(PAD0_PRESSED_GAME);
    if (picker == PICKER_OPEN)
        picker_draw();
}

/* Replaces "jal ItemUse_Spawn" @ 0x46E0F8 in the item ring: every usable item with an effect
 * object goes through here. The custom ticket asks for the picker instead. */
u8 *ticket_use_hook(int player, int id)
{
    if (id == TICKET_ID) {
        if (!in_save_room()) {
            notice_frames = NOTICE_FRAMES;
            GamePrintf("[ticket] not in a save room (stage %d room %d)\n", CUR_STAGE, CUR_ROOM);
        } else if (picker == PICKER_CLOSED) {
            picker = PICKER_PENDING;
            picker_player = player;
            picker_wait = PICKER_DELAY;
        }
        return 0;
    }
    ticket_obj = 0;
    return ItemUse_Spawn(player, id);
}

/* The two calls at the end of the ticket effect, with the effect object (s2) as an extra argument
 * (a4 = $8 for the 4-argument call, a3 for the other). */
__asm__(
    ".set push\n"
    ".set noreorder\n"
    ".globl ticket_warp_stub\n"
    "ticket_warp_stub:\n"          /* jal RequestRoomChange @ 0x47436C / 0x4743A4 */
    "    j     ticket_warp_hook\n"
    "    move  $8, $18\n"
    ".globl ticket_remove_stub\n"
    "ticket_remove_stub:\n"        /* jal Inv_RemoveItem @ 0x4743BC */
    "    j     ticket_remove_hook\n"
    "    move  $7, $18\n"
    ".set pop\n");

static int is_custom(u8 *obj)
{
    return obj && obj == ticket_obj && dest;
}

void ticket_warp_hook(int stage, int room, int objlist, int entrance, u8 *obj)
{
    if (is_custom(obj))
        RequestRoomChange(dest->stage, dest->room, dest->objlist, 0);
    else
        RequestRoomChange(stage, room, objlist, entrance);
}

/* the custom ticket is never used up (TICKET_STACK): nothing is removed */
int ticket_remove_hook(int id, int count, int unused, u8 *obj)
{
    if (!is_custom(obj))
        return Inv_RemoveItem(id, count);
    ticket_obj = 0;
    dest = 0;
    GamePrintf("[ticket] %s used (kept)\n", ticket_name);
    return 0;
}
