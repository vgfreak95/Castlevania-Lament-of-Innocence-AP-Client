/* Area Keys (AP option area_keys): each of the five areas the hub's floating rocks lead to
 * (stage 7 room 3) needs its own key, a new key item cloned into an unused key-item ID. Without
 * it, the area's rock won't lift Leon. The Archipelago Pickups patch enforces it (stagekeys.c);
 * which areas are locked comes from the client (AP_STATUS->area_locks). Header-only helpers, so
 * the debug menu (a separate binary) can use them too. Keep the order in sync with
 * apworld/lament_of_innocence/items.py AREA_KEYS (bit i of area_locks = area i). */
#ifndef STAGEKEYS_H
#define STAGEKEYS_H

#include "game.h"
#include "ap.h"

#define STAGEKEY_COUNT 5
#define STAGEKEY_ALL   ((1u << STAGEKEY_COUNT) - 1)

typedef struct {
    int stage;              /* the area's stage number (its rock's destination) */
    int item;               /* the key's item ID (unused key-item slot) */
    int clone_of;           /* the vanilla key whose info record (model, icon, sound) it copies */
    const char *area;       /* menu and "sealed" text */
    const char *key_name;
    const char *key_desc;
} StageKey;

/* Each key looks like the vanilla key its area's key door needs (rules.py): HoSR Yellow Dragon,
 * ASML Red Phoenix, DPoW Black Turtle, GFbT Blue Dragon, Theatre White Tiger. */
static const StageKey stage_keys[STAGEKEY_COUNT] = {
    { 0, 0x74, 0x5D, "House of Sacred Remains",   "Sacred Remains Key",
      "Opens the way to the House of Sacred Remains." },
    { 1, 0x75, 0x5B, "Anti-Soul Mystery Lab",     "Mystery Lab Key",
      "Opens the way to the Anti-Soul Mystery Lab." },
    { 2, 0x76, 0x5C, "Dark Palace of Waterfalls", "Waterfall Palace Key",
      "Opens the way to the Dark Palace of Waterfalls." },
    { 3, 0x77, 0x5A, "Garden Forgotten by Time",  "Forgotten Garden Key",
      "Opens the way to the Garden Forgotten by Time." },
    { 8, 0x78, 0x59, "Ghostly Theatre",           "Ghostly Theatre Key",
      "Opens the way to the Ghostly Theatre." },
};

/* pocket slot holding item `id`, or -1 */
static inline int stagekey_slot(int id)
{
    volatile short *pocket = INV_KEY_POCKET;
    int s;

    for (s = 0; s < INV_KEY_SLOTS; s++)
        if (pocket[2 * s] == id && pocket[2 * s + 1] > 0)
            return s;
    return -1;
}

static inline int stagekey_held(int i)
{
    return stagekey_slot(stage_keys[i].item) >= 0;
}

/* area i is locked and its key isn't held */
static inline int stagekey_sealed(int i)
{
    return (AP_STATUS->area_locks >> i & 1) && !stagekey_held(i);
}

/* debug menu: give / take a key directly (AP gives them as received items) */
static inline void stagekey_give(int i)
{
    if (!stagekey_held(i))
        Inv_AddItem(stage_keys[i].item, 1);
}

/* removes the key and closes the gap, so the pocket stays packed like the game keeps it */
static inline void stagekey_take(int i)
{
    volatile short *pocket = INV_KEY_POCKET;
    int s = stagekey_slot(stage_keys[i].item);

    if (s < 0)
        return;
    for (; s < INV_KEY_SLOTS - 1; s++) {
        pocket[2 * s] = pocket[2 * s + 2];
        pocket[2 * s + 1] = pocket[2 * s + 3];
    }
    pocket[2 * s] = 0;
    pocket[2 * s + 1] = 0;
}

/* Archipelago Pickups patch, every frame (stagekeys.c) */
void stagekeys_frame(void);

#endif
