/* Area Keys, part of the Archipelago Pickups patch (see stagekeys.h).
 * - Keys: five new key items in the unused key-item IDs 0x74-0x78, each a copy of a vanilla
 *   key's info record (model, icon, sound) with its own name and description. The texts are
 *   custom text IDs, which GetText (taken over with a j at its entry) answers from here. They
 *   live in the key-item pocket like any key, so they are kept in the save, and they arrive from
 *   the server like any item (pickup.c give_item -> Item_OnPickup -> Inv_AddItem).
 * - Rocks: a locked area's rock in the hub (game.h, hub warp rocks) is told Leon isn't on it
 *   (warp_rock_hook), so it never lifts; "Sealed: <area> / Needs the <key>" shows while he
 *   stands on it. As a second guard the area's door trigger boxes on that rock are kept inert:
 *   box objects (BoxObj_Update 0x454518, door records 1-5 high up and 7-11 on the floor) whose
 *   record's +0x60 flags are 4 or 6 (no vanilla lock). BoxObj_Update returns before testing the
 *   player while the object's state word (+0x3C) has 0x300 set; vanilla sets 0x200 for sealed
 *   doors (the Pagoda's: record flag 0x08 and a game flag). The centre rock (Boss Rush) also
 *   has boxes leading to stage 8, so boxes only count when they stand on an area's rock.
 * - The hub's first-visit tutorial walks Leon onto the HoSR rock after he takes Map 1; it is
 *   held back while HoSR is sealed (hub_tutorial_hook).
 * Hooks (config.toml): j gettext_hook @ 0x4552C0 (GetText entry), jal warp_rock_hook @
 * 0x67D28C / 0x67D2C4 / 0x67D33C / 0x67D3A4 (WarpRock_PlayerOn in the rock update), jal
 * hub_tutorial_stub @ 0x6B0338 (GetRoomItemFlag in the hub script). */
#include "stagekeys.h"

#define HUB_STAGE 7
#define HUB_ROOM  3

#define BOX_RECORD        0x24      /* the door record (ROOMDATA object list 0) */
#define BOX_STATE         0x3C      /* u32 */
#define BOX_STATE_SEALED  0x200
#define DOOR_FLAGS        0x60      /* u32 */
#define DOOR_FLAGS_LOCKS  0x418     /* the flags that make BoxObj_Update set 0x200 itself */

/* custom text IDs, far past the bank's 1111 entries: name = base + 2i, description = base + 2i + 1 */
#define KEY_TEXT_BASE 0x7F00
#define ITEMINFO_NAME      0
#define ITEMINFO_NAME_ALT  1        /* game mode 2 */
#define ITEMINFO_DESC      3
#define ITEMINFO_DESC_ALT  7

/* "sealed" text while Leon stands on a sealed rock, above the area logo the hub shows there */
#define SEALED_X       (-180)
#define SEALED_Y       40
#define SEALED_COLOUR  RGBA(0x80, 0x50, 0x50, 0x80)
#define LINE_HEIGHT    18

/* hub rocks 0-4 (game.h): their area's stage and x/z position (read in game) */
static const short rock_stage[STAGEKEY_COUNT] = { 8, 3, 2, 0, 1 };
static const float rock_xz[STAGEKEY_COUNT][2] = {
    { 4200, 4000 }, { 2100, 4800 }, { 3900, 4800 }, { 3000, 5200 }, { 1800, 4000 },
};
#define ROCK_BOX_RANGE 300.0f       /* x/z from the rock's centre; the circles are 400 across */

static const TextStyle sealed_style = {8, 0x80808080, 0, 0x100, 0x100, 0};

/* state lives in .bss, which the pnach never writes */
/* area index + 1 of the sealed rock Leon stood on in the last rock update, 0 = none; drawn and
 * cleared by seal_hub_warps */
static int on_sealed_rock;

/* ---- texts ---- */

/* Replaces GetText (0x4552C0) through a j at its entry (config.toml, jump hook). The delay slot
 * there (sll a0, a0, 2) still runs, so the text ID arrives multiplied by 4. */
char *gettext_hook(int id_x4)
{
    int n = (id_x4 >> 2) - KEY_TEXT_BASE;

    if (n >= 0 && n < 2 * STAGEKEY_COUNT)
        return (char *)(n & 1 ? stage_keys[n >> 1].key_desc : stage_keys[n >> 1].key_name);
    return *(char **)(TEXT_BANK + TEXT_BANK_TABLE + id_x4);
}

/* ---- items ---- */

/* Copies the vanilla keys' records into the unused slots, with the custom texts. Every frame
 * (also while frozen, before items are received): a handful of words, and a console reset
 * reloads the game's data. */
static void clone_key_records(void)
{
    int i, w;

    for (i = 0; i < STAGEKEY_COUNT; i++) {
        const u32 *src = KEYITEM_INFO(stage_keys[i].clone_of);
        u32 *dst = KEYITEM_INFO(stage_keys[i].item);

        for (w = 0; w < ITEMINFO_WORDS; w++)
            dst[w] = src[w];
        dst[ITEMINFO_NAME] = dst[ITEMINFO_NAME_ALT] = KEY_TEXT_BASE + 2 * i;
        dst[ITEMINFO_DESC] = dst[ITEMINFO_DESC_ALT] = KEY_TEXT_BASE + 2 * i + 1;
    }
}

/* ---- rocks ---- */

static int key_for_stage(int stage)
{
    int i;

    for (i = 0; i < STAGEKEY_COUNT; i++)
        if (stage_keys[i].stage == stage)
            return i;
    return -1;
}

static int in_hub(void)
{
    return CUR_STAGE == HUB_STAGE && CUR_ROOM == HUB_ROOM;
}

/* Replaces the four "jal WarpRock_PlayerOn" in the hub rock update. A sealed rock never feels
 * Leon standing on it, so it stays idle (or, if it was already counting down, hands control and
 * the camera back and settles) the way it does when he steps off. */
int warp_rock_hook(u8 *rock)
{
    u8 *rec = *(u8 **)(rock + ROCK_SPAWN_RECORD);
    int index = rec ? *(short *)(rec + ROCK_RECORD_INDEX) : -1;
    int on = WarpRock_PlayerOn(rock);
    int i;

    if (in_hub() && index >= 0 && index < STAGEKEY_COUNT
        && (i = key_for_stage(rock_stage[index])) >= 0 && stagekey_sealed(i)) {
        if (on)
            on_sealed_rock = i + 1;
        return 0;
    }
    return on;
}

/* ---- the hub's first-visit tutorial ----
 * The hub's script (0x6B0310, s2 = its object) walks Leon onto the House of Sacred Remains rock
 * once he takes Map 1 (room key 0x13F = this room, collected flag 1), until a rock has lifted him
 * once (game flag 0xC4FC0041, set by the rock while rising). States at +0x84 + 4 * depth (+0x80):
 * 2 decide -> 3 wait for the Map -> 4 take control and walk him to the rock -> 5 take control
 * every frame until the rock lifts him away. With HoSR sealed it would hold him forever, so while
 * it is sealed the script is told the Map isn't taken yet, and one already walking or holding him
 * goes back to waiting. With HoSR open (its key held, or Area Keys off) it runs as in vanilla. */
#define HOSR_KEY          0         /* stage_keys index */
#define TUTORIAL_DEPTH    0x80
#define TUTORIAL_STATES   0x84
#define TUTORIAL_DEPTHS   4
enum { TUTORIAL_WAIT_MAP = 3, TUTORIAL_WALK = 4, TUTORIAL_HOLD = 5 };

/* Replaces "jal GetRoomItemFlag" @ 0x6B0338 (its first call); passes s2, the script object, as
 * a third argument. */
__asm__(
    ".set push\n"
    ".set noreorder\n"
    ".globl hub_tutorial_stub\n"
    "hub_tutorial_stub:\n"
    "    j     hub_tutorial_hook\n"
    "    move  $6, $18\n"          /* (delay slot) a2 = s2 = the script */
    ".set pop\n");

int hub_tutorial_hook(int room_key, int index, u8 *script)
{
    int depth;

    if (!stagekey_sealed(HOSR_KEY))
        return GetRoomItemFlag(room_key, index);
    depth = *(int *)(script + TUTORIAL_DEPTH);
    if (depth >= 0 && depth < TUTORIAL_DEPTHS) {
        int *state = (int *)(script + TUTORIAL_STATES) + depth;
        if (*state == TUTORIAL_WALK || *state == TUTORIAL_HOLD)
            *state = TUTORIAL_WAIT_MAP;
    }
    return 0;
}

/* the hub rock (0-4) whose circle (x, z) is on, or -1 */
static int rock_at(const float *pos)
{
    int r;

    for (r = 0; r < STAGEKEY_COUNT; r++) {
        float dx = pos[0] - rock_xz[r][0], dz = pos[2] - rock_xz[r][1];
        if (dx * dx + dz * dz < ROCK_BOX_RANGE * ROCK_BOX_RANGE)
            return r;
    }
    return -1;
}

static void draw_sealed(int i)
{
    char line[64];

    GameSprintf(line, "Sealed: %s", stage_keys[i].area);
    DrawText(line, &sealed_style, SEALED_X, SEALED_Y, 1, SEALED_COLOUR);
    GameSprintf(line, "Needs the %s", stage_keys[i].key_name);
    DrawText(line, &sealed_style, SEALED_X, SEALED_Y + LINE_HEIGHT, 1, SEALED_COLOUR);
}

static void seal_hub_warps(void)
{
    u8 *obj = OBJ_MANAGER ? *(u8 **)OBJ_MANAGER : 0;

    for (; obj; obj = *(u8 **)(obj + OBJ_NEXT)) {
        u8 *rec;
        u32 *state;
        int i, r;

        if (*(u32 *)(obj + OBJ_UPDATE) != BOXOBJ_UPDATE_FN)
            continue;
        rec = *(u8 **)(obj + BOX_RECORD);
        if (!rec || (*(u32 *)(rec + DOOR_FLAGS) & DOOR_FLAGS_LOCKS))
            continue;           /* a door the game locks itself: leave it alone */
        if ((i = key_for_stage(*(short *)(rec + DOOR_DEST_STAGE))) < 0)
            continue;
        if ((r = rock_at((const float *)rec)) < 0 || rock_stage[r] != stage_keys[i].stage)
            continue;           /* not on that area's rock (the Boss Rush centre rock's boxes) */
        state = (u32 *)(obj + BOX_STATE);
        if (stagekey_sealed(i))
            *state |= BOX_STATE_SEALED;
        else
            *state &= ~BOX_STATE_SEALED;
    }
    if (on_sealed_rock && !IsWorldFrozen())
        draw_sealed(on_sealed_rock - 1);
    on_sealed_rock = 0;
}

void stagekeys_frame(void)
{
    clone_key_records();
    if (in_hub())
        seal_hub_warps();
}
