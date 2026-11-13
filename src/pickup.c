/* Archipelago pickups.
 * - Placed floor items with a collected flag are AP *locations*: picking one up gives nothing,
 *   reports "location N checked" and shows our own message box instead of the "Obtained" window.
 *   Location ID = GetRoomKey(stage, room) * 64 + collected-flag index (0-63 per room).
 * - Everything else (candle/enemy drops, swapped sub-weapon) stays vanilla and is just logged.
 * - Items sent by the AP server arrive in a ring at 0xFE000 (written by the client) and are given
 *   one per frame with a "Received X from Y" message; the count given is kept in the save.
 * Events go to a ring buffer at a fixed EE address, read over PINE by tools/pickup_client.py
 * (PINE only reads/writes memory, so the game can't push messages: we write, the client polls).
 * - Boss rewards (orbs, elemental whips) are AP locations too: game_key BOSS_KEY_BASE + reward index.
 * - Goal flags for the client (ap.h): Walter beaten, Death beaten (ending).
 * Hooks: jal ItemObj_Spawn @ 0x56AE8C (PlacedItem_Spawn), jal GetRoomItemFlag @ 0x56AE04
 * (PlacedItem_Spawn, for the location scan), jal ItemObj_Spawn @ 0x5761F4 (BossReward_Update),
 * jal Item_OnPickup @ 0x447A08 (ItemObj_CheckTouch), jal FrameEnd @ 0x439F08 (message box, runs
 * while the world is frozen), jal Ending_Update @ 0x43A958 (GameStateManager state 0xD). */
#include "game.h"
#include "msgbox.h"
#include "ap.h"
#include "ap_locations.h"

#define MAILBOX_MAGIC 0x50554B50 /* "PKUP" */
#define MAILBOX_SLOTS 8          /* power of two: slot = seq % MAILBOX_SLOTS */

enum { EV_PICKUP, EV_LOCATION };

typedef struct {
    u32 seq;        /* write_seq value this event was written with; lets the client detect overwrites */
    int kind;       /* EV_PICKUP (vanilla item taken) or EV_LOCATION (AP location checked) */
    int id;         /* item ID (see lament_item_table.md); for a location: the vanilla item there */
    int location;   /* AP location ID, -1 for EV_PICKUP */
    char name[64];
    char desc[176];
} PickupEvent;      /* 256 bytes */

typedef struct {
    u32 magic;
    u32 write_seq;  /* number of events written so far; bumped after the event is complete */
    u32 slot_count;
    u32 slot_size;
    PickupEvent ev[MAILBOX_SLOTS];
} PickupMailbox;

/* fixed address so the client doesn't need the map file; inside the unused 0x96000-0xFFFFF cave,
 * clear of the patch code. Never written by the pnach, so it survives across frames. */
#define MAILBOX ((volatile PickupMailbox *)0x000FC000)

/* placed items spawned in the current room: item object -> owning actor */
#define MAX_PLACED 16
static u8 *placed_obj[MAX_PLACED];
static u8 *placed_actor[MAX_PLACED];
static int placed_next;

static void copy_text(volatile char *dst, const char *src, int size)
{
    int i = 0;
    if (src)
        for (; i < size - 1 && src[i]; i++)
            dst[i] = src[i];
    dst[i] = '\0';
}

static void post_event(int kind, int id, int location)
{
    volatile PickupMailbox *mb = MAILBOX;
    u32 seq = mb->magic == MAILBOX_MAGIC ? mb->write_seq : 0;
    volatile PickupEvent *ev = &mb->ev[seq % MAILBOX_SLOTS];

    ev->seq = seq;
    ev->kind = kind;
    ev->id = id;
    ev->location = location;
    copy_text(ev->name, Item_GetNameText(id), sizeof(ev->name));
    copy_text(ev->desc, Item_GetDescText(id), sizeof(ev->desc));

    mb->slot_count = MAILBOX_SLOTS;
    mb->slot_size = sizeof(PickupEvent);
    mb->magic = MAILBOX_MAGIC;
    mb->write_seq = seq + 1;    /* last: the client only reads events below write_seq */

    if (kind == EV_LOCATION)
        GamePrintf("[pickup] #%d location %d (vanilla item %02X %s)\n", seq, location, id, Item_GetNameText(id));
    else
        GamePrintf("[pickup] #%d item %02X %s\n", seq, id, Item_GetNameText(id));
}

/* ---- spawn side ---- */

/* collected-flag index of the placed item being spawned (s7 in PlacedItem_Spawn); the actor only
 * gets it (+0x14) after ItemObj_Spawn returns */
int spawn_flag_index;   /* global: the asm stub below stores to it by name */

/* Replaces "jal ItemObj_Spawn" @ 0x56AE8C in PlacedItem_Spawn. At that point s6 = 1 when the item
 * has a collected flag, s7 = the flag index and s1 = the owning actor; all callee-saved, so the
 * stub can read them and pass the actor (or 0) as an 8th argument in a7 ($11). */
__asm__(
    ".set push\n"
    ".set noreorder\n"
    ".globl placed_spawn_stub\n"
    "placed_spawn_stub:\n"
    "    lui   $12, %hi(spawn_flag_index)\n"
    "    sw    $23, %lo(spawn_flag_index)($12)\n"   /* t4 is a temporary: free to use here */
    "    beqz  $22, 1f\n"          /* s6 == 0: not persistent, so not a location */
    "    move  $11, $0\n"          /* (delay slot, always runs) a7 = 0 */
    "    move  $11, $17\n"         /* a7 = s1 = actor */
    "1:  j     placed_spawn_hook\n"
    "    nop\n"
    ".set pop\n");

/* One line per persistent placed item that spawns, for tools/loc_scan.py: the room key and flag
 * give the AP game_key; item and position tell which ISO record (randomizer iso_offset) it is. */
static void log_placed(int id, const float *pos)
{
    int stage = GetCurrentStage() & 0xFFFF, room = GetCurrentRoom() & 0xFFFF;
    int key = GetRoomKey(stage, room);

    const u32 *bits = (const u32 *)pos;   /* exact floats: several rooms share rounded positions */
    char line[160];
    int n;

    /* the game's printf/sprintf only get the arguments passed in registers right (a0-a7), so
     * the line is built in pieces of at most 6 values */
    GameSprintf(line, "[locscan] stage %d room %d key %d flag %d item %02X ", stage, room, key,
                spawn_flag_index, id);
    for (n = 0; line[n]; n++)
        ;
    GameSprintf(line + n, "pos %d %d %d ", (int)pos[0], (int)pos[1], (int)pos[2]);
    for (; line[n]; n++)
        ;
    GameSprintf(line + n, "bits %08X %08X %08X ", bits[0], bits[1], bits[2]);
    for (; line[n]; n++)
        ;
    GameSprintf(line + n, "game_key %d", key * 64 + spawn_flag_index);
    GamePrintf("%s\n", line);
}

/* Replaces "jal GetRoomItemFlag" @ 0x56AE04 in PlacedItem_Spawn: while the location scan runs,
 * items already collected in this save spawn too, so the scan sees every location. */
int room_flag_hook(int room_key, int index)
{
    if (AP_STATUS->scan == AP_SCAN_ACTIVE)
        return 0;
    return GetRoomItemFlag(room_key, index);
}

u8 *placed_spawn_hook(int id, int group, int type, int sel, int pickup_cb, void *pos, void *rot,
                      u8 *actor)
{
    u8 *obj = ItemObj_Spawn(id, group, type, sel, pickup_cb, pos, rot);
    int i;

    if (actor)
        log_placed(id, (const float *)pos);
    if (!obj || !actor)
        return obj;
    for (i = 0; i < MAX_PLACED; i++)       /* object memory is reused: drop a stale entry */
        if (placed_obj[i] == obj)
            placed_obj[i] = 0;
    placed_obj[placed_next] = obj;
    placed_actor[placed_next] = actor;
    placed_next = (placed_next + 1) % MAX_PLACED;
    return obj;
}

/* The actor owning `obj`, if obj is a placed item with a collected flag; 0 otherwise.
 * Entries can be stale after a room change, so check the actor still owns this object. */
static u8 *find_location_actor(u8 *obj)
{
    int i;
    for (i = 0; i < MAX_PLACED; i++) {
        u8 *actor = placed_actor[i];
        if (placed_obj[i] != obj)
            continue;
        if (*(u8 **)(actor + PLACED_OBJ) == obj
            && *(int *)(actor + PLACED_ID) == *(int *)(obj + ITEMOBJ_ID)
            && (*(u16 *)(obj + ITEMOBJ_OBJFLAGS) & OBJFLAG_PERSISTENT))
            return actor;
    }
    return 0;
}

/* ---- boss rewards ----
 * BossReward_Update? (0x576120) spawns the reward as a plain pickup object with ItemObj_Spawn,
 * item = g_BossRewardTable[actor+0x20]. Only the 9 indices the AP world uses become locations;
 * the others (5 White Orb, 7 Whip of Alchemy, 11 Vampire Killer: not boss drops in the vanilla
 * game as far as known) stay vanilla. */
#define BOSS_REWARD_INDEX   0x20
#define BOSS_REWARD_COUNT   12
#define BOSS_LOCATION_MASK  0x75F   /* indices 0-4, 6, 8-10 */
#define MAX_BOSS_OBJ        4

static u8 *boss_obj[MAX_BOSS_OBJ];
static int boss_item[MAX_BOSS_OBJ];
static int boss_index[MAX_BOSS_OBJ];
static int boss_next;

/* Replaces "jal ItemObj_Spawn" @ 0x5761F4 in BossReward_Update. s1 = the reward actor
 * (callee-saved); the stub passes it as an 8th argument in a7 ($11). The original delay slot
 * (addiu t2, s1, 0x10) still runs before the stub. */
__asm__(
    ".set push\n"
    ".set noreorder\n"
    ".globl boss_spawn_stub\n"
    "boss_spawn_stub:\n"
    "    j     boss_spawn_hook\n"
    "    move  $11, $17\n"         /* (delay slot) a7 = s1 = reward actor */
    ".set pop\n");

u8 *boss_spawn_hook(int id, int group, int type, int sel, int pickup_cb, void *pos, void *rot,
                    u8 *actor)
{
    u8 *obj = ItemObj_Spawn(id, group, type, sel, pickup_cb, pos, rot);
    int index = *(int *)(actor + BOSS_REWARD_INDEX);
    int i;

    if (!obj || index < 0 || index >= BOSS_REWARD_COUNT || !(BOSS_LOCATION_MASK & (1 << index)))
        return obj;
    for (i = 0; i < MAX_BOSS_OBJ; i++)
        if (boss_obj[i] == obj)
            boss_obj[i] = 0;
    boss_obj[boss_next] = obj;
    boss_item[boss_next] = id;
    boss_index[boss_next] = index;
    boss_next = (boss_next + 1) % MAX_BOSS_OBJ;
    GamePrintf("[pickup] boss reward %d spawned (vanilla item %02X), game_key %d\n", index, id,
               BOSS_KEY_BASE + index);
    return obj;
}

/* the boss reward index of `obj`, or -1. Object memory is reused, so the item ID must still be the
 * one it spawned with. */
static int find_boss_reward(u8 *obj)
{
    int i;
    for (i = 0; i < MAX_BOSS_OBJ; i++)
        if (boss_obj[i] == obj && *(int *)(obj + ITEMOBJ_ID) == boss_item[i]) {
            boss_obj[i] = 0;
            return boss_index[i];
        }
    return -1;
}

/* ---- pickup side ---- */

/* nonzero while the PC client polls (it bumps AP_STATUS->client_ticks); it then shows its own
 * "Sent X to Y" message, so the game skips its generic one */
static u32 client_seen_ticks;
static int client_idle_frames;
#define CLIENT_TIMEOUT 180       /* frames without a poll before the game shows its own message */

static void client_watch(void)
{
    u32 ticks = AP_STATUS->client_ticks;
    if (ticks != client_seen_ticks) {
        client_seen_ticks = ticks;
        client_idle_frames = 0;
    } else if (client_idle_frames < CLIENT_TIMEOUT) {
        client_idle_frames++;
    }
}

static int client_active(void)
{
    return client_seen_ticks != 0 && client_idle_frames < CLIENT_TIMEOUT;
}

/* takes `obj` as an AP location: nothing is given, the client is told */
static void take_location(u8 *obj, int location)
{
    int vanilla = *(int *)(obj + ITEMOBJ_ID);
    char text[MSGQ_TEXT];

    /* run the normal pickup with an item that gives nothing: keeps the sound and effect */
    *(int *)(obj + ITEMOBJ_ID) = ITEM_ID_NO_EFFECT;
    Item_OnPickup(obj);
    *(int *)(obj + ITEMOBJ_ID) = vanilla;

    post_event(EV_LOCATION, vanilla, location);
    if (!client_active()) {
        GameSprintf(text, "^C80ff8080AP Location^c\nLocation %d checked\n(was: %s)",
                    location, Item_GetNameText(vanilla));
        msg_post(text);
    }
}

static int location_pickup(u8 *obj, u8 *actor)
{
    int room_key = GetRoomKey(GetCurrentStage() & 0xFFFF, GetCurrentRoom() & 0xFFFF);

    take_location(obj, room_key * 64 + *(int *)(actor + PLACED_INDEX));
    /* PlacedItem_Update still sets the collected flag next frame; this kind skips its window */
    *(int *)(actor + PLACED_KIND) = PLACED_KIND_NO_WINDOW;
    return 1;
}

/* replaces "jal Item_OnPickup" @ 0x447A08; a0 = the touched item object.
 * Returns 1 when the item was taken (the object disappears), 0 when it stays (inventory full). */
int pickup_hook(u8 *obj)
{
    u8 *actor = find_location_actor(obj);
    int id, boss;
    int taken;

    if (actor)
        return location_pickup(obj, actor);
    if ((boss = find_boss_reward(obj)) >= 0) {
        take_location(obj, BOSS_KEY_BASE + boss);
        return 1;
    }

    id = *(int *)(obj + ITEMOBJ_ID);
    taken = Item_OnPickup(obj);
    if (taken)
        post_event(EV_PICKUP, id, -1);
    return taken;
}

/* ---- receiving items ----
 * The client writes the items the AP server sent us into a ring at a fixed address; the game
 * gives them in order and keeps the number given so far in the save data, so reloading an older
 * save makes the client resend what that save doesn't have yet.
 * Client protocol: read `applied`; for each server item n >= applied (at most RECV_SLOTS ahead)
 * write ring[n % RECV_SLOTS] = {n, item, sender}; then write count = items available; magic. */
#define RECV_MAGIC 0x56434552    /* "RECV" */
#define RECV_SLOTS 16            /* power of two */

typedef struct {
    u32 index;      /* which server item this is (0, 1, 2, ...) */
    int item;       /* item ID to give */
    char sender[24];
} RecvEntry;        /* 32 bytes */

typedef struct {
    u32 magic;      /* written by the client */
    u32 count;      /* written by the client: server items available, ring holds the last ones */
    u32 applied;    /* written by the game every frame: copy of the saved counter */
    u32 reserved;
    RecvEntry ring[RECV_SLOTS];
} RecvQueue;

#define RECVQ ((volatile RecvQueue *)0x000FE000)

/* Items received so far, saved with the game: g_PlayerStatus+0x2E4 lies in the part
 * LoadPlayerStatus restores from the save (0x000-0x2E7) and was zero in a mid-game save.
 * Static check (2026-11): no load/store in the ELF uses offset 0x2E4-0x2E7 from any base and
 * nothing addresses 0xB64AE4 directly; only bulk copies/clears of the struct (LoadPlayerStatus
 * 0x467B68 and its save-side copy) touch it. Not yet confirmed with a write breakpoint. */
#define RECV_APPLIED PS_S32(0x2E4)

/* a zeroed stand-in for a pickup object, so Item_OnPickup can apply any item exactly as if it
 * was picked up (max-ups, hearts, gold, inventory items, with sound). 16-byte aligned: the game
 * reads its position with 128-bit loads. */
static u8 fake_obj[0x240] __attribute__((aligned(16)));   /* full object size */

#define ITEMOBJ_PICKUP_CB      0x130   /* index into the on-pickup callback table @ 0x7389C8 */
#define PICKUP_CB_NONE         2       /* table entry 2 is empty */

/* Item info records (Item_GetInfo 0x44B740) of usable items: u16 sell price at +0x4A (Potion
 * 100, High Potion 400: half the buy price at +0x44). Other categories are assumed to share the
 * layout; the value is clamped in case they don't. */
#define ITEMINFO_SELL_PRICE 0x4A
#define FULL_GOLD_MIN       10
#define FULL_GOLD_MAX       5000
#define FULL_GOLD_DEFAULT   50

/* gold given instead of an item that doesn't fit in the inventory */
static int full_inventory_gold(int id)
{
    u8 *info = id > 0 && id < 0xB0 ? (u8 *)Item_GetInfo(id) : 0;
    int price = info ? *(u16 *)(info + ITEMINFO_SELL_PRICE) : 0;

    if (price < FULL_GOLD_MIN || price > FULL_GOLD_MAX)
        price = FULL_GOLD_DEFAULT;
    return price;
}

/* Gives item `id`. Returns 0 when it is given, else the gold given instead (the inventory stack
 * was full: Item_OnPickup leaves such an item on the floor, and there is no floor here). */
static int give_item(int id)
{
    int i, gold;

    if (id >= 0xAA && id <= 0xAF) {    /* sub-weapon: equip it (no old one dropped on the floor) */
        SetSubWeapon(id, GetActiveOrb());
        return 0;
    }
    for (i = 0; i < (int)sizeof(fake_obj); i++)
        fake_obj[i] = 0;
    *(int *)(fake_obj + ITEMOBJ_ID) = id;
    *(int *)(fake_obj + ITEMOBJ_PICKUP_CB) = PICKUP_CB_NONE;
    if (Item_OnPickup(fake_obj))
        return 0;
    gold = full_inventory_gold(id);
    AddGold(gold);
    return gold;
}

static void recv_tick(void)
{
    volatile RecvQueue *q = RECVQ;
    volatile RecvEntry *e;
    u32 applied = RECV_APPLIED;
    char sender[sizeof(e->sender)];
    char text[MSGQ_TEXT];
    int item, gold, i;

    q->applied = applied;              /* tell the client where this save is */
    if (q->magic != RECV_MAGIC || applied >= q->count)
        return;
    if (!msgbox_game_idle() || MSGQ->head - MSGQ->tail >= MSGQ_SLOTS)
        return;                        /* wait for plain gameplay (not mid-save) and room for the message */
    e = &q->ring[applied % RECV_SLOTS];
    if (e->index != applied)
        return;                        /* the client hasn't written this item yet */

    item = e->item;
    for (i = 0; i < (int)sizeof(sender) - 1 && e->sender[i]; i++)
        sender[i] = e->sender[i];
    sender[i] = '\0';

    gold = give_item(item);
    RECV_APPLIED = applied + 1;
    q->applied = applied + 1;

    GamePrintf("[recv] #%d item %02X %s from %s\n", applied, item, Item_GetNameText(item), sender);
    if (gold) {
        GamePrintf("[recv] inventory full: $%d instead\n", gold);
        GameSprintf(text, "^C80ff8080Received^c\n%s\nfrom %s\n(no room: $%d instead)",
                    Item_GetNameText(item), sender, gold);
    } else {
        GameSprintf(text, "^C80ff8080Received^c\n%s\nfrom %s", Item_GetNameText(item), sender);
    }
    msg_post(text);
}

/* ---- goal ---- */

static int walter_room_seen;   /* been in Walter's room since boot (or the save state's boot) */

static void set_goal(u32 bits, const char *what)
{
    if ((AP_STATUS->goal & bits) == bits)
        return;
    AP_STATUS->goal |= bits;
    GamePrintf("[goal] %s\n", what);
}

/* Walter beaten = Leon reaches Death's room after having been in Walter's (the game moves him on
 * after the fight; Death's room has no other way in that we know of). Unconfirmed in game;
 * Death's ending below also counts. */
static void goal_tick(void)
{
    int stage = CUR_STAGE, room = CUR_ROOM;

    if (stage == WALTER_STAGE && room == WALTER_ROOM)
        walter_room_seen = 1;
    else if (walter_room_seen && stage == DEATH_STAGE && room == DEATH_ROOM)
        set_goal(GOAL_WALTER, "Walter defeated");
}

/* replaces "jal Ending_Update" @ 0x43A958: GameStateManager runs it every frame of state 0xD,
 * the ending sequence (its first step prints "ending movie"), which only follows Death */
int ending_hook(void)
{
    set_goal(GOAL_WALTER | GOAL_DEATH, "Death defeated, ending");
    return Ending_Update();
}

/* ---- DeathLink ----
 * Leon's deaths are counted in AP_STATUS->deaths for the client to send; a received death (the
 * client bumps AP_STATUS->kill_req) kills Leon the way the damage handler does (0x467178: HP to
 * 0, then the dead flag), once gameplay has been calm for a moment. That death isn't counted, so
 * it doesn't echo back out. The client decides whether DeathLink is on; this side just acts. */
static int was_dead;           /* Leon's dead flag last frame */
static int link_kill;          /* the next death is one we caused for a received DeathLink */
static u32 kills_done;         /* AP_STATUS->kill_req value already acted on */

static void deathlink_tick(void)
{
    volatile ApStatus *st = AP_STATUS;
    int dead = Player_TestFlag(0, PLAYER_FLAG_DEAD) != 0;

    if (dead && !was_dead) {
        if (link_kill) {
            link_kill = 0;
        } else {
            st->deaths = st->deaths + 1;
            GamePrintf("[deathlink] Leon died (%d)\n", st->deaths);
        }
    }
    was_dead = dead;

    if (st->kill_req != kills_done && !dead && msgbox_game_idle()) {
        kills_done = st->kill_req;
        link_kill = 1;
        AddHP(-PS_MAX_HP - 1.0f);                  /* clamps at 0 */
        Player_SetFlag(0, PLAYER_FLAG_DEAD, 1);
        GamePrintf("[deathlink] killed by a received death\n");
    }
}

/* ---- pickups left in this room ----
 * Bottom-right text: AP pickup locations (ap_locations.h) in the current room whose collected flag
 * isn't set yet. Hidden while the world is frozen (events, message boxes) and when the debug
 * menu's Info HUD page switches it off (AP_STATUS->hud_off). */
#define LEFT_X       70         /* screen-centre relative, like the debug menu's info HUD */
#define LEFT_Y       185
#define LEFT_LAYER   1
#define LEFT_COLOUR  RGBA(0x80, 0x80, 0x80, 0x80)

static const TextStyle left_style = {8, 0x80808080, 0, 0x100, 0x100, 0};

static void pickups_left_draw(void)
{
    int room_key, i, left = 0;
    char text[32];

    if (AP_STATUS->hud_off || IsWorldFrozen())
        return;
    room_key = GetRoomKey(CUR_STAGE, CUR_ROOM);
    for (i = 0; i < AP_PICKUP_COUNT; i++) {
        int key = ap_pickup_keys[i];
        if (key / 64 == room_key && !GetRoomItemFlag(room_key, key % 64))
            left++;
    }
    GameSprintf(text, "Pickups left: %d", left);
    DrawText(text, &left_style, LEFT_X, LEFT_Y, LEFT_LAYER, LEFT_COLOUR);
}

/* ---- per frame ---- */

/* replaces "jal FrameEnd" @ 0x439F08, the last call of GameplayFrame case 0. Unlike the debug
 * menu's hook it also runs while the world is frozen, which the message box needs. */
void frame_end_hook(void)
{
    volatile ApStatus *st = AP_STATUS;

    pickups_left_draw();     /* before FrameEnd, like the game's own HUD update */
    FrameEnd();
    if (st->magic != AP_STATUS_MAGIC) {      /* first frame after boot: clear stale RAM */
        st->goal = 0;
        st->scan = 0;
        st->client_ticks = 0;
        st->hud_off = 0;
        st->deaths = 0;
        st->kill_req = 0;
        kills_done = 0;
        link_kill = 0;
        was_dead = 0;
        st->version = AP_PROTOCOL_VERSION;
        st->magic = AP_STATUS_MAGIC;
    }
    st->version = AP_PROTOCOL_VERSION;
    client_watch();
    goal_tick();
    deathlink_tick();
    recv_tick();
    msgbox_tick();
}
