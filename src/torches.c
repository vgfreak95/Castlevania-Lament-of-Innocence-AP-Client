/* Torch Sanity: torches as AP locations (layout and protocol in torches.h). Its own patch
 * ("Archipelago Torches", base 0xB8000); the checks go to the pickups patch through
 * TORCH_CHECKS.
 *
 * Hooks (config.toml, patch.torches):
 *   jal Torch_CreateFlame @ 0x683ED0 (Torch_Create)  -> torch_flame_hook: a torch with an open
 *       table entry burns red; also logs/records torches for the debug menu
 *   jal ItemObj_Spawn @ 0x6A41D4 (Candle_Update)     -> torch_drop_stub: a red torch that breaks
 *       drops nothing; its location is checked (TF_CHECKED, TORCH_CHECKS for pickup.c) */
#include "torches.h"

#define ROOM_TORCHES 48   /* torches remembered for the current room */

#define TORCH_RED_R 0xFF
#define TORCH_RED_G 0x10
#define TORCH_RED_B 0x10

/* state lives in .bss (the pnach rewrites initialised data every frame) */
static int room_key, room_valid, room_count;   /* torches spawned in room_key so far */
static u8 *room_actor[ROOM_TORCHES];
static int room_entry[ROOM_TORCHES];           /* torch table entry, -1 = none */

static int is_weapon_item(int id)
{
    return id >= 0xAA && id <= 0xAF;
}

static int current_key(void)
{
    return GetRoomKey(CUR_STAGE, CUR_ROOM);
}

static int table_count(void)
{
    volatile TorchTable *t = TORCH_TABLE;

    if (t->magic != TORCH_TABLE_MAGIC)
        return 0;
    return t->count < TORCH_TABLE_MAX ? (int)t->count : TORCH_TABLE_MAX;
}

/* the unchecked entry for the torch at (key, x, z), or -1 */
static int find_entry(int key, u32 x_bits, u32 z_bits)
{
    volatile TorchEntry *e = TORCH_TABLE->entry;
    int i, n = table_count();

    for (i = 0; i < n; i++)
        if (e[i].room_key == key && e[i].x_bits == x_bits && e[i].z_bits == z_bits)
            return (e[i].flags & TF_CHECKED) ? -1 : i;
    return -1;
}

/* recolours a flame for good: the emitter's three sprite prims get their colour once, at spawn */
static void flame_red(u8 **fx)
{
    u8 *emitter;
    int n;

    if (!fx || !(emitter = *fx))
        return;
    *(volatile u32 *)(emitter + FLAME_EMITTER_RGBA) =
        0x80000000 | (TORCH_RED_B << 16) | (TORCH_RED_G << 8) | TORCH_RED_R;
    for (n = 0; n < 3; n++) {
        FLAME_PRIM_COLOUR(emitter, n)[0] = TORCH_RED_R;
        FLAME_PRIM_COLOUR(emitter, n)[1] = TORCH_RED_G;
        FLAME_PRIM_COLOUR(emitter, n)[2] = TORCH_RED_B;
    }
}

/* ---- debug menu support (TORCH_SCAN) ---- */

/* the game's printf only gets values passed in registers right, so the line goes in pieces */
static void log_torch(int index, int item, int kind, int flame, const float *pos)
{
    const u32 *bits = (const u32 *)pos;
    char line[160];
    int n;

    GameSprintf(line, "[torch] stage %d room %d key %d n %d item %02X ", CUR_STAGE, CUR_ROOM,
                room_key, index, item);
    for (n = 0; line[n]; n++)
        ;
    GameSprintf(line + n, "kind %d flame %d pos %d %d %d ", kind, flame, (int)pos[0], (int)pos[1],
                (int)pos[2]);
    for (; line[n]; n++)
        ;
    GameSprintf(line + n, "bits %08X %08X %08X", bits[0], bits[1], bits[2]);
    GamePrintf("%s\n", line);
}

static void record_torch(int index, int item, int kind, int flame, const float *pos)
{
    volatile TorchScanTable *t = TORCH_SCAN;
    const u32 *bits = (const u32 *)pos;
    volatile TorchSeen *r;
    u32 i;

    if (t->magic != TORCH_SCAN_MAGIC || t->count > TORCH_SCAN_MAX) {
        t->count = 0;
        t->seq = 0;
        t->magic = TORCH_SCAN_MAGIC;
    }
    for (i = 0; i < t->count; i++)
        if (t->rec[i].key == room_key && t->rec[i].x_bits == bits[0] && t->rec[i].z_bits == bits[2])
            return;
    if (t->count >= TORCH_SCAN_MAX)
        return;
    r = &t->rec[t->count];
    r->key = room_key;
    r->stage = CUR_STAGE;
    r->room = CUR_ROOM;
    r->item = item;
    r->kind = kind;
    r->flame = flame;
    r->index = index;
    r->x_bits = bits[0];
    r->y_bits = bits[1];
    r->z_bits = bits[2];
    t->count++;
    t->seq++;
}

/* ---- spawn ---- */

/* replaces jal Torch_CreateFlame in Torch_Create (0x683ED0): the candle is set up (item, kind,
 * position) and this makes its flame */
u8 **torch_flame_hook(u8 *actor, int flame, int kind)
{
    u8 **fx = Torch_CreateFlame(actor, flame, kind);
    const float *pos = (const float *)(actor + CANDLE_POS);
    const u32 *bits = (const u32 *)pos;
    int item = *(int *)(actor + CANDLE_ITEM);
    int key = current_key();
    u32 debug = TORCH_SCAN->flags;
    int index, e = -1;

    if (!room_valid || key != room_key) {
        room_valid = 1;
        room_key = key;
        room_count = 0;
    }
    index = room_count++;
    if (debug & TS_LOG)
        log_torch(index, item, kind, flame, pos);
    if (debug & TS_RECORD)
        record_torch(index, item, kind, flame, pos);

    if (!is_weapon_item(item)) {
        e = find_entry(key, bits[0], bits[2]);
        if (e >= 0) {
            /* Candle_Update only calls ItemObj_Spawn (our check) for an item > 0: a torch with
             * none (every torch in Joachim mode) gets the small heart it would drop anyway */
            if (item <= 0)
                *(int *)(actor + CANDLE_ITEM) = ITEM_SMALL_HEART;
            flame_red(fx);
        }
    }
    if (index < ROOM_TORCHES) {
        room_actor[index] = actor;
        room_entry[index] = e;
    }
    return fx;
}

/* the open table entry of a candle in the current room that burns red, or -1. Looked up again by
 * position: the client may have rewritten the table since the torch spawned. */
static int actor_entry(u8 *actor)
{
    const u32 *bits = (const u32 *)(actor + CANDLE_POS);
    int i;

    if (!actor || !room_valid || current_key() != room_key)
        return -1;
    for (i = 0; i < room_count && i < ROOM_TORCHES; i++)
        if (room_actor[i] == actor)
            return room_entry[i] >= 0 ? find_entry(room_key, bits[0], bits[2]) : -1;
    return -1;
}

/* queues a check for pickup.c; 0 when the ring is full (pickups patch off or not running) */
static int queue_check(u32 game_key, int item, const float *pos)
{
    volatile TorchChecks *c = TORCH_CHECKS;
    volatile TorchCheck *k;

    if (c->magic != TORCH_CHECKS_MAGIC || c->head - c->tail > TORCH_CHECKS_MAX) {
        c->head = 0;
        c->tail = 0;
        c->magic = TORCH_CHECKS_MAGIC;
    }
    if (c->head - c->tail >= TORCH_CHECKS_MAX)
        return 0;
    k = &c->check[c->head % TORCH_CHECKS_MAX];
    k->game_key = game_key;
    k->item = item;
    k->pos[0] = pos[0];
    k->pos[1] = pos[1];
    k->pos[2] = pos[2];
    c->head = c->head + 1;   /* last: pickup.c reads checks below head */
    return 1;
}

/* Replaces jal ItemObj_Spawn @ 0x6A41D4 in Candle_Update; s2 = the candle (callee-saved), passed
 * on as an 8th argument in a7 ($11). The original delay slot (addiu t2, sp, 0x30) still runs. */
__asm__(
    ".set push\n"
    ".set noreorder\n"
    ".globl torch_drop_stub\n"
    "torch_drop_stub:\n"
    "    j     torch_drop_hook\n"
    "    move  $11, $18\n"         /* (delay slot) a7 = s2 = candle */
    ".set pop\n");

/* The candle already made its drop out of +0x34 (hearts for IDs >= 0xB0, a big heart when a 0-9
 * roll equals the ID, $1/$5 for full hearts); a red torch drops nothing and checks its location.
 * Candle_Update only tests the result for NULL (then 0x44B530 spawns a heart-kind item as an
 * actor instead) and drops it, so a red torch returns a non-NULL dummy to skip that too. */
u8 *torch_drop_hook(int id, int group, int type, int sel, int pickup_cb, void *pos, void *rot,
                    u8 *actor)
{
    volatile TorchTable *t = TORCH_TABLE;
    int e = actor_entry(actor);
    u32 game_key;

    if (e < 0)
        return ItemObj_Spawn(id, group, type, sel, pickup_cb, pos, rot);
    game_key = t->entry[e].game_key;
    if (!queue_check(game_key, id, (const float *)pos)) {
        GamePrintf("[torch] game_key %d: check ring full, vanilla drop\n", game_key);
        return ItemObj_Spawn(id, group, type, sel, pickup_cb, pos, rot);
    }
    t->entry[e].flags |= TF_CHECKED;
    t->checked_seq = t->checked_seq + 1;
    GamePrintf("[torch] game_key %d checked (would drop %02X)\n", game_key, id);
    return (u8 *)1;
}
