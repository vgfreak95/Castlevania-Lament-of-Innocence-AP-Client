/* Shop Sanity (src/apshop.c, part of the Menu and Minimap patch): Rinaldo sells AP locations.
 *
 * The client (game_interface.py sync_shop) writes the shop table at SHOP_TABLE: which of the 15
 * vanilla shop items stay on sale (`vanilla`, SV_* bits) and one entry per AP shop slot with its
 * game_key, price, look (icon/model) and the text the shop shows. A slot that isn't checked is on
 * the Buy list; buying it charges the price, gives nothing, sets its `checked` and `report`
 * words, and the Archipelago Pickups patch (pickup.c) reports it as EV_LOCATION and clears
 * `report`. A checked slot is sold out (off the list). No table (magic 0, e.g. Shop Sanity off):
 * the vanilla shop.
 *
 * Shop list (RE, SLUS-20733): Shop_BuildList? 0x6E0FE8(sell, buf) fills the 1200-byte list at
 * 0xBAC678 (12-byte entries {draw fn, item ID, greyed}, 0-terminated: 99 rows) with every item
 * ID of the shop's six item kinds (0x79A478: usable, key, armour, orbs, accessories, relics) that
 * Shop_ItemState? 0x6E06B0 doesn't rule out (3 = not sold: buy price 0, or a held max-1 item).
 * There is no stock array: an item is on sale while its info record has a buy price. So every
 * AP row needs an item ID of its own with an info record the shop accepts; the IDs nothing else
 * uses (SHOP_IDS) are 20, so at most SHOP_SHOWN_MAX AP slots are on the list at once. The table
 * holds more (SHOP_SLOTS_MAX): the first SHOP_SHOWN_MAX unchecked slots, in table order, get the
 * IDs each time the list is built, so a bought slot's row goes to the next one.
 *
 * Keep in sync with apworld/lament_of_innocence/game_interface.py. */
#ifndef APSHOP_H
#define APSHOP_H

#include "game.h"

#define SHOP_KEY_BASE    0x20000   /* AP shop slot i: game_key SHOP_KEY_BASE + i (ap.h) */
#define SHOP_EVENT_ID    0x100     /* EV_LOCATION's item field for shop slot i: SHOP_EVENT_ID + i */

#define SHOP_TABLE_MAGIC 0x504F4853   /* "SHOP" */
#define SHOP_SLOTS_MAX   64
#define SHOP_SHOWN_MAX   20        /* item IDs for AP rows (SHOP_IDS in apshop.c) */
#define SHOP_NAME_BYTES  32
#define SHOP_DESC_BYTES  160

/* vanilla shop items (bit i of ShopTable.vanilla = item stays on sale) */
#define SV_POTION        0x0001    /* 0x2A */
#define SV_HIGH_POTION   0x0002    /* 0x2B */
#define SV_SERUM         0x0004    /* 0x2F */
#define SV_UNCURSE       0x0008    /* 0x30 */
#define SV_MAGICAL       0x0010    /* 0x31 Magical Ticket */
#define SV_MEMORIAL      0x0020    /* 0x32 Memorial Ticket */
#define SV_DIAMOND       0x0040    /* 0x3C */
#define SV_RUBY          0x0080    /* 0x3D */
#define SV_SAPPHIRE      0x0100    /* 0x3E */
#define SV_OPAL          0x0200    /* 0x3F */
#define SV_TURQUOISE     0x0400    /* 0x40 */
#define SV_ZIRCON        0x0800    /* 0x41 */
#define SV_MUSIC_BOX     0x1000    /* 0x60 */
#define SV_DOLL          0x2000    /* 0x1A Sacrificial Doll */
#define SV_WHITE_BISHOP  0x4000    /* 0x8C */
#define SV_ALL           0x7FFF

/* ShopSlot.look: icon and model of the row (gems: model 0x31 and its palettes) */
enum { SHOP_LOOK_FILLER, SHOP_LOOK_USEFUL, SHOP_LOOK_PROGRESSION, SHOP_LOOK_COUNT };

#define SHOP_PRICE_MIN   2         /* the Member Plate discount (x0.9 per one worn) must not
                                      round a price to 0: the shop divides by it */
#define SHOP_PRICE_MAX   30000     /* usable items keep the buy price in an s16 */

typedef struct {
    u32 game_key;     /* reported in EV_LOCATION */
    u32 price;        /* buy price (clamped to SHOP_PRICE_MIN..SHOP_PRICE_MAX) */
    u32 look;         /* SHOP_LOOK_* */
    u32 checked;      /* nonzero: sold out (set by the client from the server, and by the game
                         when it's bought) */
    u32 report;       /* set by the game when bought; pickup.c posts EV_LOCATION and clears it */
    u32 reserved[3];
    char name[SHOP_NAME_BYTES];   /* Buy list row (cp932, NUL-terminated; ~18 characters fit) */
    char desc[SHOP_DESC_BYTES];   /* description box (\n line breaks; 2 lines of ~40 fit) */
} ShopSlot;           /* 224 bytes */

typedef struct {
    u32 magic;        /* SHOP_TABLE_MAGIC, written last by the client */
    u32 count;        /* AP slots (<= SHOP_SLOTS_MAX) */
    u32 vanilla;      /* SV_* bits: vanilla items that stay on sale */
    u32 checked_seq;  /* bumped by the game whenever it checks a slot */
    u32 reserved[4];
    ShopSlot slot[SHOP_SLOTS_MAX];
} ShopTable;          /* 0xB4000-0xB7820, below the debug menu's map mailbox (0xB7F00) */

#define SHOP_TABLE ((volatile ShopTable *)0x000B4000)

/* apshop.c */
char *shop_text(int text_id);   /* the slot text for a shop text ID, or 0 (item_text_hook) */
void apshop_frame(void);        /* every frame (ticket_frame_hook): info records */

#endif
