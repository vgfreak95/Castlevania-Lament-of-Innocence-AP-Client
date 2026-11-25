/* Archipelago traps, part of the Archipelago Pickups patch (see traps.h).
 *
 * The player update (0x460590) clears the per-frame player flags, runs the hit check (0x464238:
 * the attacks touching Leon's body, *(player + 0x2F4)) and then the state machine (0x469598 on
 * player +0x330), which moves Leon to a new state through the current state's transition table.
 * Player flags are u16 words at player +0xC30; a flag mask is (word << 16) | bits (Player_SetFlag
 * 0x461398 -> 0x46D988). Words 0-7 and 12-15 are cleared every frame, so a raised hit flag lives
 * one frame: the state machine has to take it that frame or it is gone.
 * State machine (player +0x330): +0x00 state, +0x04 state table (0x758BE8; +0x08 + state * 4 ->
 * state def), +0x08 player index, +0x48 reset request: when set, the next run puts Leon in state
 * 0 (idle, controllable) without evaluating any transition. Player_ResetState (0x462C18) sets it
 * and zeroes the move speed (0x462090); the game calls it for events and doors. 0x461F70 returns
 * the state. State def: +0x00 animation, +0x08 transition count, +0x0C transitions, 0x20 bytes
 * each: +0x00 anim frame window (s16 hi, s16 lo; -1 = always), +0x04/+0x08 conditions, +0x0C
 * player flag mask, +0x10 target state (s16, -1 = none), +0x12 callback (s16 index into the
 * table at 0x73DD80; 30 = 0x46B380, which runs the damage handler 0x467178), +0x14 f32,
 * +0x18/+0x1C callback args. The first entry that matches with a target wins.
 * Hits: every controllable state (0x00-0x95 except a few) has "flag 0x10004 (hit) -> 0x97" (or
 * -> 0x98 in the air, 0x96 for some), dispatcher states (no animation) that pick the reaction from
 * the hit flags: 0x97: 0x11000 -> 0xAA (launch), 0x10400/0x10800 -> 0xA8/0xA9 (hurt), 0x18000 ->
 * 0x9F, 0x20001 -> 0x9E (stagger), 0x50040 -> 0xA3, 0x50100 -> 0xA2; 0x98 (air): 0x11000 -> 0xB0.
 * The hit-reaction states themselves have NO hit transition: the stagger recoveries 0xA0/0xA1,
 * the flinches 0xA5-0xA9 and the whole knockback chain 0xAA (launch) -> 0xAB/0xAC (flying,
 * landing), 0xAD (down, getting up: -> 0x04 or 0x00 from frame 0x0F/0x1E), 0xB0 (air launch),
 * 0xB1-0xB5, 0xB7. So a hit raised while Leon is in one of them is dropped (this, not an
 * invincibility timer, is what swallowed a second Knockback Trap: the damage reaction ran and
 * raised 0x11000, nothing took it). 0xA2 paralyzed, 0xA3/0xA4 stoned, 0xB6 and 0xB8-0xBC (death)
 * are left alone. The damage reaction's only other gate is player flag 0x90008, which turns any
 * attack without flag 0x800 into 0x10080 (no reaction); the hit check's own gates (flag 0x50200,
 * player +0x2D4, the +0x2C8 timer) are skipped by calling the reaction directly.
 * The trap replaces the jal of the hit check (@ 0x460714) with knock_hook, which runs the check
 * and then raises what an enemy hit would.
 *
 * Ailments: bits of g_PlayerStatus+0x2F4: 0x1 poison, 0x2 stone, 0x4 curse, 0x8 paralysis. Each
 * has an update (0x4770B8 poison, 0x477CC0 stone, 0x477730 curse, 0x4783A8 paralysis) that
 * starts it, with its timer and colour, when its bit is set or its hit flag is raised; setting
 * the bit alone gives only that, not the effect. In vanilla the ailment comes with a hit: the hit
 * puts Leon in the hurt state (0xA8/0xA9), whose damage handler (0x467178) raises the ailment's
 * hit flag (0x50020 poison, 0x50040 stone, 0x50080 curse, 0x50100 + 0x60040 paralysis) from the
 * attack's record, and the hurt state's table moves him on: 0x50040 -> 0xA3 (stoned, held until
 * he mashes free), 0x50100 -> 0xA2 (paralyzed). The idle state's table has no such entries.
 * Curse and poison have no state: curse switches the whip skills off until it wears off; poison
 * takes 1 HP every 2.8-4 s (with a flinch, state 0xA6), never below 1 HP, for up to 32 s (less
 * with luck).
 * So an ailment trap does the same: a light hit with no damage, then its hit flags for
 * AILMENT_FRAMES frames while the hurt state runs (checked in game: stone and paralysis reach
 * their states, curse turns the skills off, poison drains HP).
 *
 * Knockback: for each hit the check calls the damage reaction
 * 0x464698(player, body, attack), which for an attack with flag 0x10 (attack +0x150) raises the
 * heavy-hit flags (0x18000, 0x10004) and sets the knockback direction (player +0x230) from the
 * attack's velocity (+0x140) or, without one, from where it is (+0x20 for attack type +0x04 = 0).
 * With a knockback pending, knock_hook feeds the damage reaction a made-up attack with no damage,
 * coming at Leon from the front, flagged heavy (0x10) and launch (0x80, which raises 0x11000: the
 * launch state 0xAA), so he is smacked backwards across the room. With no flags it is a light hit
 * (0x10400/0x10800: the hurt state), which the ailment traps use.
 * A made-up hit only fires from a state whose table takes the hit flag (fire_ready). From a
 * hit-reaction state (above) the hook first calls Player_ResetState, so Leon is back in state 0
 * the next frame and the hit lands from there: a Knockback Trap during a knockback launches him
 * again. Not within KNOCK_MIN_FRAMES of a trap's own launch, so two traps arriving together
 * still give two visible knockbacks. A knockback only counts once Leon is seen in the launch
 * state (0xAA, 0xB0 in the air) the frame after; otherwise it is tried again, so none is lost.
 *
 * Hook (config.toml): jal knock_hook @ 0x460714. */
#include "traps.h"

#define PS_AILMENTS    PS_S32(0x2F4)
#define AILMENT_STONE      0x2
#define AILMENT_CURSE      0x4
#define AILMENT_PARALYSIS  0x8
/* player flags the damage handler raises to start each ailment (see above) */
#define AILMENT_HIT_POISON     0x50020
#define AILMENT_HIT_STONE      0x50040
#define AILMENT_HIT_CURSE      0x50080
#define AILMENT_HIT_PARALYSIS  0x50100
#define AILMENT_HIT_PARALYSIS2 0x60040    /* raised with it */
#define AILMENT_FRAMES         20         /* frames the hit flags are raised for after the hit */

#define PLAYER_BODY        0x2F4       /* player struct (0xB632C0 + n * 0x1500): hit-check body */
#define ATTACK_TYPE        0x04        /* 0: position at +0x20 */
#define ATTACK_POS         0x20
#define ATTACK_ID          0x10
#define ATTACK_VELOCITY    0x140
#define ATTACK_FLAGS       0x150
#define ATTACK_DAMAGE      0x154
#define ATTACK_FLAG_HEAVY  0x10
#define ATTACK_FLAG_LAUNCH 0x80        /* raises 0x11000: thrown across the room */
#define KNOCK_FROM         100.0f      /* the made-up attack starts this far in front of Leon */
/* Heavy + launch is the "smacked across the stage" knockback: ~2400-2900 units back in the open
 * (checked in game), against ~300 for the heavy flag alone, which is only the stagger. The attack
 * ID makes no visible difference; 0x68 (one the damage reaction special-cases) is what was tested. */
#define KNOCK_ATTACK_ID    0x68
#define KNOCK_FLAGS        (ATTACK_FLAG_HEAVY | ATTACK_FLAG_LAUNCH)
#define KNOCK_MAX_PENDING  3
#define KNOCK_MIN_FRAMES   40          /* a trap's launch runs this long before the next resets it */

/* player state machine (see above) */
#define PL_STATE           0x330
#define PL_STATE_TABLE     0x334
#define STATE_COUNT        0xBD
#define SDEF_COUNT         0x08
#define SDEF_TRANSITIONS   0x0C
#define TR_SIZE            0x20
#define TR_FLAG            0x0C
#define TR_TARGET          0x10        /* s16 */
#define HIT_FLAG           0x10004
#define ST_LAUNCH          0xAA
#define ST_AIR_LAUNCH      0xB0

static const char *const names[TRAP_COUNT] = {
    "Paralysis Trap", "Curse Trap", "Stone Trap", "Knockback Trap", "Poison Trap",
};

void PlayerHitCheck(int player, u8 *pl);                    /* 0x464238 */
void Player_DamageReaction(int player, u8 *body, u8 *attack);  /* 0x464698 */
void Player_GetFacing(int player, float *out);              /* 0x460C30: vec4, player +0x1B0 */
void Player_ResetState(int player);                         /* 0x462C18: state 0 next run */

/* state lives in .bss, which the pnach never writes */
static u8 fake_attack[0x160] __attribute__((aligned(16)));
static int knock_pending;           /* knockbacks still to do */
static int knock_fired;             /* a knockback was raised last frame: check it took */
static int knock_wait;              /* frames before a trap's launch may be reset */
static u32 ailment_pending;         /* AILMENT_HIT_* flags of ailment traps received */
static u32 ailment_active;          /* the ones being applied */
static int ailment_frames;          /* frames left raising them */

const char *trap_name(int id)
{
    return names[id - TRAP_ITEM_BASE];
}

void trap_give(int id)
{
    switch (id - TRAP_ITEM_BASE) {
    case TRAP_PARALYSIS: ailment_pending |= AILMENT_HIT_PARALYSIS; break;
    case TRAP_CURSE:     ailment_pending |= AILMENT_HIT_CURSE; break;
    case TRAP_STONE:     ailment_pending |= AILMENT_HIT_STONE; break;
    case TRAP_POISON:    ailment_pending |= AILMENT_HIT_POISON; break;
    case TRAP_KNOCKBACK:
        if (knock_pending < KNOCK_MAX_PENDING)
            knock_pending++;
        break;
    }
}

static void knock_back(u8 *pl, u32 flags)
{
    float *pos = (float *)(fake_attack + ATTACK_POS);
    float *vel = (float *)(fake_attack + ATTACK_VELOCITY);
    float face[4] __attribute__((aligned(16)));
    u8 *body = *(u8 **)(pl + PLAYER_BODY);
    int i;

    if (!body)
        return;
    for (i = 0; i < (int)sizeof(fake_attack); i++)
        fake_attack[i] = 0;
    Player_GetFacing(0, face);
    *(int *)(fake_attack + ATTACK_TYPE) = 0;
    *(int *)(fake_attack + ATTACK_ID) = KNOCK_ATTACK_ID;
    for (i = 0; i < 3; i++) {
        pos[i] = PLAYER_POS[i] + face[i] * KNOCK_FROM;   /* in front of Leon */
        vel[i] = -face[i];                         /* coming at him */
    }
    pos[3] = vel[3] = 1.0f;
    *(u32 *)(fake_attack + ATTACK_FLAGS) = flags;
    *(float *)(fake_attack + ATTACK_DAMAGE) = 0.0f;
    Player_DamageReaction(0, body, fake_attack);
}

/* whether state `st`'s transition table takes the hit flag (ignores the frame windows) */
static int takes_hit(u8 *pl, int st)
{
    u8 *table = *(u8 **)(pl + PL_STATE_TABLE);
    u8 *def, *tr;
    int n;

    if (!table || st < 0 || st >= STATE_COUNT)
        return 0;
    def = *(u8 **)(table + 8 + st * 4);
    if (!def)
        return 0;
    tr = *(u8 **)(def + SDEF_TRANSITIONS);
    for (n = *(int *)(def + SDEF_COUNT); n > 0; n--, tr += TR_SIZE)
        if (*(u32 *)(tr + TR_FLAG) == HIT_FLAG && *(short *)(tr + TR_TARGET) != -1)
            return 1;
    return 0;
}

/* the hit-reaction states that drop hits (stagger recovery, flinch, knockback; see above) */
static int hit_reaction(int st)
{
    return (st >= 0xA0 && st <= 0xB7) && !(st >= 0xA2 && st <= 0xA4) && st != 0xB6;
}

/* 1 if a made-up hit would be taken now. From a hit-reaction state, asks the game to put Leon
 * back in state 0 (taken this frame), so it fires the frame after. */
static int fire_ready(u8 *pl)
{
    int st = *(int *)(pl + PL_STATE);

    if (takes_hit(pl, st))
        return 1;
    if (hit_reaction(st) && knock_wait <= 0) {
        Player_ResetState(0);
        GamePrintf("[trap] reset from state %x\n", st);
    }
    return 0;
}

/* Replaces "jal PlayerHitCheck" in the player update (@ 0x460714). */
void knock_hook(int player, u8 *pl)
{
    int st;

    PlayerHitCheck(player, pl);
    if (player != 0)
        return;
    if (knock_wait > 0)
        knock_wait--;
    if (Player_TestFlag(0, PLAYER_FLAG_DEAD))
        return;                     /* wait: nothing while dead */
    if (knock_fired) {
        /* last frame's knockback: it counts if the state machine took it */
        knock_fired = 0;
        st = *(int *)(pl + PL_STATE);
        if (st == ST_LAUNCH || st == ST_AIR_LAUNCH) {
            knock_pending--;
            knock_wait = KNOCK_MIN_FRAMES;
            GamePrintf("[trap] knockback\n");
        }
    }
    if (ailment_frames > 0) {
        /* the hit's hurt state is running: raise the ailment's hit flags the way the damage
         * handler (0x467178) does from there, so its transition table starts the ailment */
        ailment_frames--;
        if (ailment_active & AILMENT_HIT_PARALYSIS & 0xFFFF) {
            Player_SetFlag(0, AILMENT_HIT_PARALYSIS2, 1);
            Player_SetFlag(0, AILMENT_HIT_PARALYSIS, 1);
        }
        if (ailment_active & AILMENT_HIT_CURSE & 0xFFFF) Player_SetFlag(0, AILMENT_HIT_CURSE, 1);
        if (ailment_active & AILMENT_HIT_STONE & 0xFFFF) Player_SetFlag(0, AILMENT_HIT_STONE, 1);
        if (ailment_active & AILMENT_HIT_POISON & 0xFFFF) Player_SetFlag(0, AILMENT_HIT_POISON, 1);
        return;
    }
    if (ailment_pending && !(PS_AILMENTS & AILMENT_STONE)) {
        /* first a light hit with no damage, which puts Leon in the hurt state */
        if (!fire_ready(pl))
            return;
        ailment_active = ailment_pending;
        ailment_pending = 0;
        ailment_frames = AILMENT_FRAMES;
        knock_back(pl, 0);
        GamePrintf("[trap] ailment %x\n", ailment_active);
        return;
    }
    if (knock_pending <= 0 || (PS_AILMENTS & AILMENT_STONE))
        return;                     /* wait: no knockback while turned to stone */
    if (!fire_ready(pl))
        return;
    knock_back(pl, KNOCK_FLAGS);
    knock_fired = 1;
}
