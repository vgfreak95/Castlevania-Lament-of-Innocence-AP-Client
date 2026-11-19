/* Savewarp Ticket (part of the Minimap patch; ticket.c): a new usable item in the unused slot
 * 0x4D, a copy of the Memorial Ticket (0x32) with its own name, description and a red model and
 * icon. Sold in Rinaldo's shop (not an AP item: the apworld never places it). Used in a save
 * room, it opens a picker of the save rooms Leon has visited (savewarps.h); the picked one plays
 * the Memorial Ticket's effect (glow, sound, Leon fading out), then warps there. The ticket is
 * reusable: it is never used up. */
#ifndef TICKET_H
#define TICKET_H

#include "game.h"

#define TICKET_ID          0x4D    /* first unused usable item (category 4 is 0x2A-0x54) */
#define TICKET_CLONE_OF    0x32    /* Memorial Ticket */

/* Palette of the ticket's model: item record +0x28, which goes into the TEX0 CSA field (the CLUT
 * offset) of the model's texture. The tickets share model 0x30: Memorial uses palette 0, Magical
 * palette 1; palette 2 is empty in the game and gets a red one (ticket.c). */
#define TICKET_PALETTE 2

/* Rinaldo's shop: its Items tab lists every usable ID 0x2A-0x54 whose buy price isn't 0 (list
 * built at 0x6E0FE8, filtered by 0x6E06B0), so slot 0x4D shows up once it has a price. Buy price
 * = s16 at record +0x44, sell price = s16 at +0x46 (0x6B79B8 / 0x6B7A38); the Memorial Ticket is
 * 800 / 400. Buy 0 = not sold; sell 0 = left out of the Sell list.
 * With a max stack of 1 the shop drops it from the Buy list while Leon has one (0x6E06B0), so it
 * can be bought once; it can't be sold, so it can't be lost that way either. */
#define TICKET_PRICE      2000
#define TICKET_SELL_PRICE 0
#define TICKET_STACK      1     /* most Leon can hold (record +0x34) */

/* usable item pocket: 43 slots of (s16 id, s16 count) */
#define TICKET_POCKET      ((volatile short *)(PLAYER_STATUS + 0xF4))
#define TICKET_POCKET_SLOTS 43

/* how many Leon has (inline, so the debug menu can use it without linking ticket.c) */
static inline int ticket_count(void)
{
    int s;

    for (s = 0; s < TICKET_POCKET_SLOTS; s++)
        if (TICKET_POCKET[2 * s] == TICKET_ID)
            return TICKET_POCKET[2 * s + 1];
    return 0;
}

/* +1, up to TICKET_STACK */
static inline void ticket_give(void)
{
    if (ticket_count() < TICKET_STACK)
        Inv_AddItem(TICKET_ID, 1);
}

#endif
