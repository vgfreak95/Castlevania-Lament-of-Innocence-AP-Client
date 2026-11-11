/* Shared message queue for the game's message box ("Obtained" window).
 * The queue lives at a fixed EE address, so any patch (and the PC client over PINE) can post to
 * it; the Archipelago Pickups patch (msgbox.c) shows the messages one at a time. */
#ifndef MSGBOX_H
#define MSGBOX_H

#include "game.h"

#define MSGQ_SLOTS 8      /* power of two */
#define MSGQ_TEXT  128

typedef struct {
    u32 head;             /* messages posted so far; slot = head % MSGQ_SLOTS */
    u32 tail;             /* messages shown so far */
    char text[MSGQ_SLOTS][MSGQ_TEXT];
} MsgQueue;

/* fixed address in the unused 0x96000-0xFFFFF cave, after the pickup mailbox (0xFC000) */
#define MSGQ ((volatile MsgQueue *)0x000FD000)

/* Queue `text` (\n line breaks, ^Crrggbbaa colour, ^c colour reset). Returns 0 if the queue is full. */
static inline int msg_post(const char *text)
{
    volatile MsgQueue *q = MSGQ;
    volatile char *dst;
    int i;

    if (q->head - q->tail >= MSGQ_SLOTS)
        return 0;
    dst = q->text[q->head % MSGQ_SLOTS];
    for (i = 0; i < MSGQ_TEXT - 1 && text[i]; i++)
        dst[i] = text[i];
    dst[i] = '\0';
    q->head = q->head + 1;    /* last: the box only shows complete messages */
    return 1;
}

/* Show queued messages; call once per frame, also on frozen frames (see frame_end_hook). */
void msgbox_tick(void);

#endif
