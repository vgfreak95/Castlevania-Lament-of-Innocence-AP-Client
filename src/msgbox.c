/* Shows the messages in the shared queue (msgbox.h) in the game's message box, one at a time,
 * using the same open/close sequence as PlacedItem_Update / PlacedItem_MsgBoxTick. */
#include "msgbox.h"

#define MSG_MIN_FRAMES 20  /* ignore a confirm in the first frames (button may still be held) */

/* Frames of plain gameplay (world not frozen, not paused, no game message box) needed before a
 * popup opens or a received item is given. Multi-step game sequences such as saving have short
 * gaps between their own boxes; opening ours in such a gap (and unfreezing the world when it
 * closes) left the save sequence waiting forever. */
#define IDLE_FRAMES 15
#define WORLD_PAUSED_BITS (*(volatile u8 *)0x00B36750)   /* World_SetPausedBit: bit 0 */

static int box_open;       /* our message is showing */
static int box_frames;     /* frames it has been open */
static int idle_frames;    /* consecutive frames of plain gameplay, capped at IDLE_FRAMES */

static int game_busy(u8 *box)
{
    return IsWorldFrozen() || (WORLD_PAUSED_BITS & 1) || *(volatile int *)(box + MSGBOX_OPEN_FLAG);
}

int msgbox_game_idle(void)
{
    return !box_open && idle_frames >= IDLE_FRAMES;
}

void msgbox_tick(void)
{
    volatile MsgQueue *q = MSGQ;
    u8 *box = MsgBox_Get();

    if (!box_open) {
        if (game_busy(box))
            idle_frames = 0;
        else if (idle_frames < IDLE_FRAMES)
            idle_frames++;
        if (q->head == q->tail || idle_frames < IDLE_FRAMES)
            return;                       /* nothing to show, or the game is busy; next frame */
        World_Freeze(0);
        World_SetPausedBit(1);
        Sound_StopLoops();
        Pad_StopVibration(0, -1);
        MsgBox_Open(MSGBOX_STYLE_OBTAINED, (const char *)q->text[q->tail % MSGQ_SLOTS], 2);
        *(float *)(box + 0x64) = 0.4f;    /* scale values the game sets for this window */
        *(float *)(box + 0x68) = 0.1f;
        *(float *)(box + 0x6C) = 0.1f;
        *(float *)(box + 0x70) = 0.1f;
        box_open = 1;
        box_frames = 0;
        idle_frames = 0;
        return;
    }

    {
        int done = MsgBox_Update(box);
        MsgBox_Draw(box);
        box_frames++;
        if (done && box_frames > MSG_MIN_FRAMES) {
            MsgBox_Close(box);
            /* we only open from plain gameplay, so the freeze and pause bit are ours to undo */
            World_Unfreeze();
            World_SetPausedBit(0);
            box_open = 0;
            q->tail = q->tail + 1;        /* the slot is free only once the box no longer shows it */
        }
    }
}
