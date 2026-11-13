/* Archipelago: fixed EE addresses shared by the Archipelago Pickups patch (pickup.c), the debug
 * menu's location scan (submenus/locscan.c) and the PC client over PINE
 * (apworld/lament_of_innocence/game_interface.py). All of them live in the unused 0x96000-0xFFFFF
 * cave, outside every patch's code and data, so the pnach never rewrites them. Keep in sync with
 * game_interface.py. */
#ifndef AP_H
#define AP_H

#include "game.h"

/* 0xFC000 event mailbox (pickup.c), 0xFD000 message queue (msgbox.h), 0xFE000 receive ring
 * (pickup.c). This block sits between the mailbox (ends 0xFC810) and the message queue. */
typedef struct {
    u32 magic;          /* AP_STATUS_MAGIC, written by pickup.c every frame */
    u32 version;        /* AP_PROTOCOL_VERSION */
    u32 goal;           /* GOAL_* bits, sticky until the console resets */
    u32 scan;           /* AP_SCAN_ACTIVE while the debug menu's location scan runs */
    u32 client_ticks;   /* bumped by the PC client on every poll; lets the game know one is there */
    u32 hud_off;        /* nonzero: hide the "pickups left" counter (debug menu, Info HUD page) */
    u32 deaths;         /* DeathLink, written by the game: Leon's deaths since boot, not counting
                           ones it caused for a received DeathLink */
    u32 kill_req;       /* DeathLink, written by the client: bumped for every received death; the
                           game kills Leon once per change */
} ApStatus;

#define AP_STATUS ((volatile ApStatus *)0x000FCF00)
#define AP_STATUS_MAGIC     0x54535041   /* "APST" */
#define AP_PROTOCOL_VERSION 3
#define AP_SCAN_ACTIVE      0x4E414353   /* "SCAN" */

#define GOAL_WALTER 0x1     /* Walter beaten: went from his room straight into Death's */
#define GOAL_DEATH  0x2     /* Death beaten: the ending sequence started */

/* rooms for the goal checks (bosses.c) */
#define WALTER_STAGE 5
#define WALTER_ROOM  0x30
#define DEATH_STAGE  5
#define DEATH_ROOM   0x29

/* Boss rewards (BossReward_Update? 0x576120): the reward actor's +0x20 indexes the 12-int table
 * g_BossRewardTable @ 0x7AF590 (ISO offset 0x44F590, the randomizer's boss locations). Their AP
 * game_key is BOSS_KEY_BASE + index; placed items use room_key * 64 + flag (< 416 * 64). */
#define BOSS_KEY_BASE 0x8000

#endif
