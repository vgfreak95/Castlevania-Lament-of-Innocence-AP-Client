/* Received-item notices ("toasts"): a small line per item the AP server sent, in the bottom-right
 * corner (top right when the minimap is in the bottom-right corner), shown for about a second and
 * then faded out. Drawn by the Archipelago Pickups patch (toast.c, from frame_end_hook); the
 * minimap patch only tells it when the bottom-right corner is taken.
 *
 * The state sits at a fixed address in the unused 0x96000-0xFFFFF cave, between the message queue
 * (0xFD000-0xFD408, msgbox.h) and the receive ring (0xFE000, pickup.c): the pickups patch has
 * almost no room for .bss below its mailbox (0xFC000), and the minimap patch must reach
 * use_top. Not read or written by the PC client.
 *
 * use_top protocol: minimap.c sets it on every frame its corner is the bottom right (its panel or,
 * hidden, its "Checks left" counter is there); toast.c reads it on the same frame (frame_end_hook
 * runs after the minimap's hook) and clears it. Set: the toasts go at the top right, stacking
 * down; clear: at the bottom right, stacking up from the bottom edge. */
#ifndef TOAST_H
#define TOAST_H

#include "game.h"

#define TOAST_MAGIC 0x54534F54   /* "TOST" */
#define TOAST_LINES 4            /* lines on screen at once; more items wait in the receive ring */
#define TOAST_TEXT  128

typedef struct {
    int age;                     /* frames shown so far */
    int width;                   /* measured width at `scale`, in screen pixels */
    int scale;                   /* TextStyle scale_x = scale_y (0x100 = 1.0) */
    char text[TOAST_TEXT];       /* ^C40ff40aa "Received" ^c name...; aa = alpha, set per frame */
} ToastLine;                     /* 140 bytes */

typedef struct {
    u32 magic;                   /* TOAST_MAGIC once toast.c has set it up */
    int use_top;                 /* written by minimap.c, see above */
    u32 first;                   /* ring of the lines shown: line[(first + i) % TOAST_LINES] */
    u32 count;
    ToastLine line[TOAST_LINES];
} ToastArea;                     /* 0xFD800-0xFDA40 */

#define TOAST ((ToastArea *)0x000FD800)   /* not volatile: only game-thread code touches it */


/* toast.c (pickups patch): queue a line for an item. `sender` may be 0; gold != 0: the item
 * didn't fit and that much gold was given instead. Returns 0 (nothing queued) when all
 * TOAST_LINES are in use. */
int toast_push(const char *name, const char *sender, int gold);
int toast_full(void);
/* once per frame, also on frozen frames (it draws and ages nothing then) */
void toast_frame(void);

#endif
