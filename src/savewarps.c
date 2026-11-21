/* Save rooms for the Savewarp Ticket (savewarps.h, ticket.c).
 * - Save rooms: the pieces with the save flag (PIECE_FLAG_SAVE, drawn red) in
 * the pause map files of every area, read from the disc's FILEDATA.BIN (seven
 * map files; stage 4 has no save room). Numbered per area in room order: "HoSR:
 * Save 1" is the lowest room number.
 * - Object list: every save room loads the same room file (FILEDATA.BIN
 * +0x174C2F0, 20 object lists). The list decides where the exit door leads, so
 * a warp has to arrive with the room's own list, or the exit takes Leon to
 * another save room's corridor. Each room's list is the one its corridor door
 * uses, read from the disc. List 4 is unused.
 * - Visited: bit 0 of the room's state word (game.h ROOM_STATE), the pause
 * map's own flag, which is kept in the save, so the list survives a console
 * reset. */
#include "savewarps.h"

/* in the apworld's area order (regions.py AREAS) */

/* stage, room, object list, save number, area */
const SaveRoom save_rooms[] = {
    {7, 9, 12, 1, "Main Castle"},
    {0, 69, 2, 1, "HoSR"},    {0, 70, 3, 2, "HoSR"},    {0, 73, 17, 3, "HoSR"},
    {1, 52, 0, 1, "ASML"},    {1, 53, 1, 2, "ASML"},    {1, 54, 16, 3, "ASML"},
    {2, 0, 7, 1, "DPoW"},     {2, 55, 5, 2, "DPoW"},    {2, 56, 6, 3, "DPoW"},
    {3, 61, 8, 1, "GFbT"},    {3, 62, 9, 2, "GFbT"},    {3, 63, 10, 3, "GFbT"},
    {3, 64, 18, 4, "GFbT"},
    {8, 55, 13, 1, "Theatre"}, {8, 56, 14, 2, "Theatre"}, {8, 57, 15, 3, "Theatre"},
    {5, 0, 11, 1, "PotMM"},
    {6, 5, 19, 1, "PoET"},
};
const int save_room_count = (int)(sizeof(save_rooms) / sizeof(save_rooms[0]));

int save_room_visited(const SaveRoom *s) {
  u32 *table = ROOM_STATE;
  int key;

  if (!table || !ROOM_TABLE)
    return 0;
  key = GetRoomKey(s->stage, s->room);
  if (key < 0 || key >= ROOM_STATE_COUNT)
    return 0;
  return table[key * 3] & 1;
}

/* ---- names ----
 * The save file list (title screen load/save) names a save's room with the game's own table
 * at 0x798848 (read by 0x6C6E78): 22 entries of {room key, area text ID, floor text ID or -1},
 * printed "%s %s" (or "%s" without a floor), e.g. 0x45 -> 746 "House of Sacred Remains" +
 * 738 "1F". Several save rooms share a name (GFbT's four are all "Garden Forgotten By Time 1F"),
 * so those get a number in save_rooms order. */
#define SAVE_NAMES       ((const int *)0x00798848)
#define SAVE_NAME_COUNT  22

/* the room's entry in the game's table, or 0 */
static const int *save_name(const SaveRoom *s) {
  int key = GetRoomKey(s->stage, s->room), i;

  for (i = 0; i < SAVE_NAME_COUNT; i++)
    if (SAVE_NAMES[i * 3] == key)
      return &SAVE_NAMES[i * 3];
  return 0;
}

static int same_name(const int *a, const int *b) {
  return a && b && a[1] == b[1] && a[2] == b[2];
}

void save_room_label(const SaveRoom *s, char *buf) {
  const int *e = save_name(s);
  int i, nth = 0, total = 0;

  if (!e) { /* not in the game's table: the area abbreviation */
    GameSprintf(buf, "%s: Save %d", s->area, s->number);
    return;
  }
  for (i = 0; i < save_room_count; i++)
    if (same_name(save_name(&save_rooms[i]), e)) {
      total++;
      if (&save_rooms[i] == s)
        nth = total;
    }
  if (e[2] < 0)
    GameSprintf(buf, "%s", GetText(e[1]));
  else
    GameSprintf(buf, "%s %s", GetText(e[1]), GetText(e[2]));
  if (total > 1) {
    for (i = 0; buf[i]; i++)
      ;
    GameSprintf(buf + i, " %d", nth);
  }
}

int save_room_here(const SaveRoom *s) {
  return CUR_STAGE == s->stage && CUR_ROOM == s->room;
}

int in_save_room(void) {
  int i;

  for (i = 0; i < save_room_count; i++)
    if (save_room_here(&save_rooms[i]))
      return 1;
  return 0;
}
