/* Shows the messages in the shared queue (msgbox.h) in the game's message box, one at a time,
 * using the same open/close sequence as PlacedItem_Update / PlacedItem_MsgBoxTick. */
#include "msgbox.h"

#define MSG_MIN_FRAMES 20  /* ignore a confirm in the first frames (button may still be held) */

static int box_open;       /* our message is showing */
static int box_frames;     /* frames it has been open */

void msgbox_tick(void)
{
    volatile MsgQueue *q = MSGQ;
    u8 *box = MsgBox_Get();

    if (!box_open) {
        if (q->head == q->tail)
            return;
        if (*(volatile int *)(box + MSGBOX_OPEN_FLAG))
            return;                       /* the game's own box is showing; try again next frame */
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
        return;
    }

    {
        int done = MsgBox_Update(box);
        MsgBox_Draw(box);
        box_frames++;
        if (done && box_frames > MSG_MIN_FRAMES) {
            MsgBox_Close(box);
            World_Unfreeze();
            World_SetPausedBit(0);
            box_open = 0;
            q->tail = q->tail + 1;        /* the slot is free only once the box no longer shows it */
        }
    }
}
