/* Savewarps (an Archipelago Menu page, apmenu.h): warp to any save room Leon has been in.
 * - Save rooms: the pieces with the save flag (PIECE_FLAG_SAVE, drawn red) in the pause map
 *   files of every area, read from the disc's FILEDATA.BIN (seven map files; stage 4 has no
 *   save room). Numbered per area in room order: "HoSR: Save 1" is the lowest room number.
 *   The list is shared with the Savewarp Ticket (savewarps.h, ticket.c).
 * - Visited: bit 0 of the room's state word (game.h ROOM_STATE), the pause map's own flag, which
 *   is kept in the save, so the list survives a console reset.
 * - Warp: RequestRoomChange(stage, room, 0, 0), as a door does, arriving at the room's first
 *   entrance. Only offered while Leon is alive. */
#include "apmenu.h"
#include "savewarps.h"

/* in the apworld's area order (regions.py AREAS) */
const SaveRoom save_rooms[] = {
    { 7,  9, 1, "PttDA" },
    { 0, 69, 1, "HoSR" },    { 0, 70, 2, "HoSR" },    { 0, 73, 3, "HoSR" },
    { 1, 52, 1, "ASML" },    { 1, 53, 2, "ASML" },    { 1, 54, 3, "ASML" },
    { 2,  0, 1, "DPoW" },    { 2, 55, 2, "DPoW" },    { 2, 56, 3, "DPoW" },
    { 3, 61, 1, "GFbT" },    { 3, 62, 2, "GFbT" },    { 3, 63, 3, "GFbT" },
    { 3, 64, 4, "GFbT" },
    { 8, 55, 1, "Theatre" }, { 8, 56, 2, "Theatre" }, { 8, 57, 3, "Theatre" },
    { 5,  0, 1, "PotMM" },
    { 6,  5, 1, "PoET" },
};
#define SAVE_ROOM_COUNT ((int)(sizeof(save_rooms) / sizeof(save_rooms[0])))
const int save_room_count = SAVE_ROOM_COUNT;

/* state lives in .bss, which the pnach never writes */
static u8 shown[SAVE_ROOM_COUNT];   /* save_rooms indexes of the visited ones */
static int shown_count;

int save_room_visited(const SaveRoom *s)
{
    u32 *table = ROOM_STATE;
    int key;

    if (!table || !ROOM_TABLE)
        return 0;
    key = GetRoomKey(s->stage, s->room);
    if (key < 0 || key >= ROOM_STATE_COUNT)
        return 0;
    return table[key * 3] & 1;
}

int save_room_here(const SaveRoom *s)
{
    return CUR_STAGE == s->stage && CUR_ROOM == s->room;
}

int in_save_room(void)
{
    int i;

    for (i = 0; i < SAVE_ROOM_COUNT; i++)
        if (save_room_here(&save_rooms[i]))
            return 1;
    return 0;
}

static void refresh(void)
{
    int i;

    shown_count = 0;
    for (i = 0; i < SAVE_ROOM_COUNT; i++)
        if (save_room_visited(&save_rooms[i]))
            shown[shown_count++] = i;
}

static int warps_rows(void)
{
    return shown_count ? shown_count : 1;
}

static void warps_text(int row, char *out)
{
    const SaveRoom *s;

    if (!shown_count) {
        GameSprintf(out, "No save rooms visited yet");
        return;
    }
    s = &save_rooms[shown[row]];
    GameSprintf(out, "%s: Save %d%s", s->area, s->number, save_room_here(s) ? " (here)" : "");
}

static void warps_help(int row, char *out)
{
    GameSprintf(out, shown_count ? "Cross warp  Triangle back" : "Triangle back");
}

static void warps_confirm(int row)
{
    const SaveRoom *s;

    if (!shown_count || row >= shown_count || Player_TestFlag(0, PLAYER_FLAG_DEAD))
        return;
    s = &save_rooms[shown[row]];
    GamePrintf("[savewarp] %s: Save %d (stage %d room %d)\n", s->area, s->number, s->stage,
               s->room);
    apmenu_close();
    RequestRoomChange(s->stage, s->room, 0, 0);
}

AP_PAGE(savewarps_page, 020) = {
    .title     = "Savewarps",
    .row_count = warps_rows,
    .row_text  = warps_text,
    .confirm   = warps_confirm,
    .help      = warps_help,
    .open      = refresh,
};
