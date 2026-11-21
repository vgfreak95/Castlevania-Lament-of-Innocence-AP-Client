/* Archipelago traps, part of the Archipelago Pickups patch (traps.c). Trap items use IDs past
 * every real item, like the skills (skills.h): pickup.c give_item hands them to trap_give. */
#ifndef TRAPS_H
#define TRAPS_H

#include "game.h"

#define TRAP_ITEM_BASE  0x210       /* apworld items.json game_id 528-531 */
enum { TRAP_PARALYSIS, TRAP_CURSE, TRAP_STONE, TRAP_KNOCKBACK, TRAP_COUNT };

static inline int trap_item(int id)
{
    return id >= TRAP_ITEM_BASE && id < TRAP_ITEM_BASE + TRAP_COUNT;
}

void trap_give(int id);             /* springs trap item `id` (trap_item(id)) */
const char *trap_name(int id);

#endif
