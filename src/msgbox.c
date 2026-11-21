/* Shows the messages in the shared queue (msgbox.h) in the game's message box, one at a time,
 * using the same open/close sequence as PlacedItem_Update / PlacedItem_MsgBoxTick. */
#include "msgbox.h"

#define MSG_MIN_FRAMES 20  /* ignore a confirm in the first frames (button may still be held) */

/* Frames of plain gameplay (world not frozen, not paused, no game message box) needed before a
 * popup opens or a received item is given. Multi-step game sequences such as saving have short
 * gaps between their own boxes; opening ours in such a gap (and unfreezing the world when it
 * closes) left the save sequence waiting forever. */
#define IDLE_FRAMES 15

/* World state bits @ 0xB36750 (one setter per bit, 0x438600-0x4387FC). Plain gameplay has only
 * 0x800 (set by GameStateManager). Busy:
 *   0x0001  paused (World_SetPausedBit)
 *   0x0020, 0x0040  World_Freeze (IsWorldFrozen only tests bit 0)
 *   0x4000  the save sequence: set from the save prompt until its last step, which comes ~0.7 s
 *           after a cancelled save's prompt closes and calls MsgBox_Close on the shared box.
 *           Seen in game (2026-11-15); its setter isn't identified. */
#define WORLD_STATE_BITS (*(volatile u32 *)0x00B36750)
#define WORLD_BUSY_BITS  0x4061

static int box_open;       /* our message is showing */
static int box_frames;     /* frames it has been open */
static int idle_frames;    /* consecutive frames of plain gameplay, capped at IDLE_FRAMES */

static int game_busy(u8 *box)
{
    return IsWorldFrozen() || (WORLD_STATE_BITS & WORLD_BUSY_BITS)
        || *(volatile int *)(box + MSGBOX_OPEN_FLAG);
}

/* we only open from plain gameplay, so the freeze and pause bit are ours to undo */
static void end_popup(void)
{
    World_Unfreeze();
    World_SetPausedBit(0);
    box_open = 0;
    idle_frames = 0;
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

    /* The box is shared: game code that closes it (MsgBox_Close clears the open flag) takes our
     * popup away, and it would never report confirmed. Give the world back and show the same
     * message again once the game is idle. */
    if (!*(volatile int *)(box + MSGBOX_OPEN_FLAG)) {
        GamePrintf("[msgbox] popup closed by the game; showing it again later\n");
        end_popup();
        return;
    }

    {
        int done = MsgBox_Update(box);
        MsgBox_Draw(box);
        box_frames++;
        if (done && box_frames > MSG_MIN_FRAMES) {
            MsgBox_Close(box);
            end_popup();
            q->tail = q->tail + 1;        /* the slot is free only once the box no longer shows it */
        }
    }
}

/* Door prompts (0x4542E0: a door's message or yes/no question, run by its trigger box) open the
 * shared box and freeze the world, but when answered (state 2) only unfreeze: they never call
 * MsgBox_Close, so the box's open flag stays set after the text is gone. Nothing in the game
 * minds, but our idle checks (and the minimap's) read the flag, so popups, received items and the
 * minimap stayed stuck until some other game code closed the box. Replaces the
 * "jal World_SetFreezeBit" (a0 = 0) in that state @ 0x4544DC: close the box, then unfreeze. */
void door_prompt_done_hook(int on)
{
    u8 *box = MsgBox_Get();

    if (box && *(volatile int *)(box + MSGBOX_OPEN_FLAG))
        MsgBox_Close(box);
    World_SetFreezeBit(on);
}
