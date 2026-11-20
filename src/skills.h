/* Whip skills as Archipelago items, part of the Archipelago Pickups patch (skills.c).
 * The game keeps the learned skills in one mask, g_PlayerStatus+0x2A4 (saved with the game),
 * bit i = skill i below. Skill items use IDs past every real item (SKILL_ITEM_BASE + bit), which
 * pickup.c give_item turns into a bit of that mask. */
#ifndef SKILLS_H
#define SKILLS_H

#include "game.h"

#define SKILL_COUNT       15
#define SKILL_ITEM_BASE   0x200     /* item ID of skill bit 0; apworld items.json game_id 512-526 */
#define SKILLS_LEARNED    (*(volatile u32 *)(PLAYER_STATUS + 0x2A4))

/* bits (the unlock table at 0x759658, names at 0x73DC90):
 * 0 Extension, 1 Draw Up, 2 Vertical High, 3 Rising Shot, 4 Fast Rising, 5 Spinning Blast,
 * 6 Energy Blast, 7 Sonic Edge, 8 A Extension 1, 9 A Extension 2, 10 Step Attack,
 * 11 Falcon Claw, 12 Quick Step, 13 Quick Step 2, 14 Perfect Guard */
#define SKILL_QUICK_STEP    0x1000
#define SKILL_PERFECT_GUARD 0x4000

static inline int skill_item(int id)
{
    return id >= SKILL_ITEM_BASE && id < SKILL_ITEM_BASE + SKILL_COUNT;
}

void skill_give(int id);            /* learns skill item `id` (skill_item(id)) */
const char *skill_name(int id);     /* the game's name of skill item `id` */

#endif
