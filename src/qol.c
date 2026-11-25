/* Quality-of-life options, part of the Archipelago Pickups patch. The client writes the
 * options' bits into AP_STATUS->qol every poll (0 after a console reset until it does).
 *
 * Wolf's Foot (QOL_WOLFS_FOOT): relics are used through the table at 0x76F350 (11 entries of
 * 0x18 bytes, by relic index, Wolf's Foot first): +0x00 start function, +0x04 the move bits it
 * turns on, +0x0C float "duration". While a relic runs, 0x485B28 spends
 * 200 / (duration * k) MP per second (k = 1.5 with accessory 0x20 equipped, else 1), and the relic
 * stops when MP runs out. Wolf's Foot's duration is 20 (10 MP a second); the option sets the drain
 * to a percentage of that (duration 20 * 100 / percent), 0% being a duration so long it never
 * drains. Written every frame: a console reset reloads the game's data, and turning the option
 * off puts the vanilla value back. */
#include "qol.h"
#include "ap.h"

#define RELIC_TABLE        0x0076F350
#define RELIC_STRIDE       0x18
#define RELIC_DURATION     0x0C
#define RELIC_WOLFS_FOOT   0               /* relic index (item 0x86) */
#define WOLFS_FOOT_VANILLA 20.0f
#define WOLFS_FOOT_NO_DRAIN 1.0e30f       /* 0%: 200 / duration rounds to nothing */

#define RELIC_DURATION_OF(i) \
    (*(volatile float *)(RELIC_TABLE + (i) * RELIC_STRIDE + RELIC_DURATION))

void qol_frame(void)
{
    u32 qol = AP_STATUS->qol;
    int pct = QOL_WOLFS_FOOT_PCT(qol);
    float want = WOLFS_FOOT_VANILLA;

    if ((qol & QOL_WOLFS_FOOT) && pct < 100)
        want = pct ? WOLFS_FOOT_VANILLA * 100.0f / pct : WOLFS_FOOT_NO_DRAIN;

    if (RELIC_DURATION_OF(RELIC_WOLFS_FOOT) != want)
        RELIC_DURATION_OF(RELIC_WOLFS_FOOT) = want;
}
