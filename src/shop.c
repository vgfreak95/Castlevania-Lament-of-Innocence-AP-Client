/* Rinaldo's shop, part of the Archipelago Pickups patch: equipment that is in the AP item pool
 * isn't sold, so it can only come from the multiworld.
 * The shop's Buy list shows an item only while its buy price isn't 0 (0x6E06B0 via 0x6E0630 ->
 * 0x6B79B8). For armour (item type 2, records 0x84 bytes from 0x739978) and accessories (type 3,
 * 0x84 bytes from 0x739B88) the buy price is the int at +0x44; +0x48 is the sell price, left as is
 * so these items can still be sold. Written every frame: a console reset reloads the game's data. */
#include "shop.h"

#define ARMOUR_FIRST     0x06
#define ARMOUR_INFO      0x00739978
#define ACCESSORY_FIRST  0x0A
#define ACCESSORY_INFO   0x00739B88
#define EQUIP_STRIDE     0x84
#define EQUIP_BUY_PRICE  0x44

static const u8 not_sold[] = {
    0x06, 0x07, 0x08, 0x09,     /* Earth, Meteor, Moonlight, Solar Plate */
    0x18,                       /* Mobius's Brooch */
    0x22,                       /* Jade Mask */
};

static volatile int *buy_price(int id)
{
    u32 rec = id < ACCESSORY_FIRST
        ? ARMOUR_INFO + (id - ARMOUR_FIRST) * EQUIP_STRIDE
        : ACCESSORY_INFO + (id - ACCESSORY_FIRST) * EQUIP_STRIDE;

    return (volatile int *)(rec + EQUIP_BUY_PRICE);
}

void shop_frame(void)
{
    int i;

    for (i = 0; i < (int)sizeof(not_sold); i++) {
        volatile int *price = buy_price(not_sold[i]);
        if (*price)
            *price = 0;
    }
}
