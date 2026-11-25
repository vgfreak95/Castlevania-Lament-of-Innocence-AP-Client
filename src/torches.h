/* Torch Sanity (src/torches.c, the Archipelago Torches patch): torches as AP locations.
 *
 * A torch is found by its room key and spawn position (x/z float bits): torches come from room
 * actor records, so the position is the same on every visit.
 *
 * The client (game_interface.py) writes the torch table at TORCH_TABLE: one entry per torch
 * location of the slot, with the location's game_key. A torch with an entry that isn't checked
 * yet burns red; breaking it drops nothing, sets TF_CHECKED and checks the location (through
 * TORCH_CHECKS: pickup.c reports it). Torches without an entry, checked ones and weapon torches
 * stay vanilla. No table (magic 0, e.g. Torch Sanity off): every torch is vanilla.
 *
 * TORCH_SCAN is for the debug menu's Torches page: it sets TORCH_SCAN->flags to have every torch
 * that spawns logged and/or recorded there (tools/torch_rando.py scan reads it).
 *
 * The tables sit in the unused 0x96000-0xFFFFF cave; keep in sync with game_interface.py and
 * the debug tools' tools/torch_rando.py. */
#ifndef TORCHES_H
#define TORCHES_H

#include "game.h"

#define TORCH_KEY_BASE 0x10000   /* torch game_key = TORCH_KEY_BASE + n (data/torches.json) */
#define ITEM_SMALL_HEART 0x93    /* a candle's drop when its record has none */

/* ---- torch table, written by the client ---- */
#define TORCH_TABLE_MAGIC 0x48435254   /* "TRCH" */
#define TORCH_TABLE_MAX   1536
#define TF_CHECKED        0x1          /* location checked: vanilla torch (set by both sides) */

typedef struct {
    u16 room_key;     /* GetRoomKey(stage, room) */
    u16 reserved;     /* 0 (unused: a red torch drops nothing) */
    u32 x_bits;       /* spawn position x, z as float bits */
    u32 z_bits;
    u32 game_key;     /* reported in EV_LOCATION */
    u32 flags;        /* TF_CHECKED */
} TorchEntry;         /* 20 bytes */

typedef struct {
    u32 magic;        /* TORCH_TABLE_MAGIC, written last by the client */
    u32 count;
    u32 checked_seq;  /* bumped by the game whenever it sets TF_CHECKED */
    u32 reserved;
    TorchEntry entry[TORCH_TABLE_MAX];
} TorchTable;         /* 0xC0000-0xC7810 */

#define TORCH_TABLE ((volatile TorchTable *)0x000C0000)

/* ---- debug scan buffer ---- */
#define TORCH_SCAN_MAGIC 0x4E435354    /* "TSCN" */
#define TORCH_SCAN_MAX   1600
#define TS_LOG           0x1           /* TORCH_SCAN->flags: print every torch that spawns */
#define TS_RECORD        0x2           /* ... and add it to rec[] */

typedef struct {
    u16 key;
    u8 stage, room;
    u8 item;          /* the torch's own drop (0x93 small heart when its record has none) */
    u8 kind;          /* candle kind (+0x30) */
    u8 flame;         /* flame type: 0 normal, 1 sub-weapon torch */
    u8 index;         /* spawn order in the room */
    u32 x_bits, y_bits, z_bits;
} TorchSeen;          /* 20 bytes */

typedef struct {
    u32 magic;        /* TORCH_SCAN_MAGIC once anything was recorded */
    u32 count;
    u32 seq;          /* bumped on every new record */
    u32 flags;        /* TS_*, written by the debug menu */
    TorchSeen rec[TORCH_SCAN_MAX];
} TorchScanTable;     /* 0xC8000-0xCFD10, below the Free Camera patch (0xD0000) */

#define TORCH_SCAN ((volatile TorchScanTable *)0x000C8000)

/* ---- torch checks, from the torches patch to the pickups patch ----
 * The torch hooks are their own patch ("Archipelago Torches", torches.c, base 0xB8000: the
 * pickups patch is full up to its mailbox), so the two talk through this fixed ring: torches.c
 * adds a check when a red torch breaks (it drops nothing), pickup.c's frame_end_hook reports it
 * as EV_LOCATION. head and tail count checks added / reported; slot = count % TORCH_CHECKS_MAX. */
#define TORCH_CHECKS_MAGIC 0x4B434354  /* "TCCK" */
#define TORCH_CHECKS_MAX   8           /* power of two */

typedef struct {
    u32 game_key;     /* the torch location's game_key */
    int item;         /* what the candle would have dropped (for the log and message) */
    float pos[3];     /* where the drop would have been (pickup sound) */
} TorchCheck;         /* 20 bytes */

typedef struct {
    u32 magic;        /* TORCH_CHECKS_MAGIC: written by torches.c before its first check */
    u32 head;         /* checks added (torches.c) */
    u32 tail;         /* checks reported (pickup.c) */
    u32 reserved;
    TorchCheck check[TORCH_CHECKS_MAX];
} TorchChecks;        /* 0xC7900-0xC79B0 */

#define TORCH_CHECKS ((volatile TorchChecks *)0x000C7900)   /* between the table and TORCH_SCAN */

#endif
