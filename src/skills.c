/* Whip skills as Archipelago items, part of the Archipelago Pickups patch (see skills.h).
 * - Vanilla: every frame 0x46F098 walks the unlock table at 0x759658 (16 entries of 20 bytes:
 *   the skill bit, then the move's ability word and three conditions, each u16 value + u16 type:
 *   1 total kills, 2 kinds of enemy, 5 Quick Steps, 6 guards, 7 Perfect Guards; Sonic Edge has two
 *   entries, one per way to learn it). For a skill not learned it switches the move off and calls
 *   0x46F480 with the three conditions; when they hold it sets the skill's bit in the learned mask
 *   (and in the "Learned new technique!!" popup's queue, object +0x18C). For a learned skill it
 *   switches the move on, unless g_PlayerStatus+0x2F4 has bit 4 (another game mode).
 * - Archipelago: the condition check (jal 0x46F480 @ 0x46F418) goes through skill_check_hook,
 *   which only lets it pass for the skills in AP_STATUS->skill_vanilla (written by the client
 *   from the Basic Skills option; 0 after a console reset until the client writes it, so nothing
 *   is learned the normal way before it connects). Every other skill is learned only when its item
 *   arrives; the game's own loop then switches the move on.
 * Hook (config.toml): jal skill_check_stub @ 0x46F418. */
#include "skills.h"
#include "ap.h"

#define SKILL_TEXTS ((const int *)0x0073DC90)   /* 15 x 4 text IDs, [0] = the skill's name */

int Skill_CheckConditions(u8 *obj, u32 cond1, u32 cond2, u32 cond3);   /* 0x46F480 */

/* Replaces "jal 0x46F480" in the unlock loop; passes s1, the table entry, as a fifth argument
 * ($8). The call's delay slot (lw a3) has already run. */
__asm__(
    ".set push\n"
    ".set noreorder\n"
    ".globl skill_check_stub\n"
    "skill_check_stub:\n"
    "    j     skill_check_hook\n"
    "    move  $8, $17\n"          /* (delay slot) a4 = s1 = the unlock table entry */
    ".set pop\n");

int skill_check_hook(u8 *obj, u32 cond1, u32 cond2, u32 cond3, const u32 *entry)
{
    if (!(AP_STATUS->skill_vanilla & entry[0]))
        return 0;                  /* an AP item: never learned the normal way */
    return Skill_CheckConditions(obj, cond1, cond2, cond3);
}

void skill_give(int id)
{
    SKILLS_LEARNED |= 1u << (id - SKILL_ITEM_BASE);
}

const char *skill_name(int id)
{
    return GetText(SKILL_TEXTS[(id - SKILL_ITEM_BASE) * 4]);
}
