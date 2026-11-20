/* The save rooms (savewarps.c) the Savewarp Ticket (ticket.c) lists and warps to. */
#ifndef SAVEWARPS_H
#define SAVEWARPS_H

#include "game.h"

typedef struct {
    u8 stage, room;
    u8 objlist;     /* its object list in the shared save room file: picks the exit */
    u8 number;      /* "Save n" within its area */
    const char *area;
} SaveRoom;

extern const SaveRoom save_rooms[];
extern const int save_room_count;

int save_room_visited(const SaveRoom *s);   /* Leon has been in it (the pause map's flag) */
int save_room_here(const SaveRoom *s);      /* Leon is in it now */
int in_save_room(void);                     /* Leon is in one of them now */

/* Writes the room's name as the save file list shows it ("House of Sacred Remains 1F"), with
 * " n" added when several save rooms share that name. buf holds at least SAVE_LABEL_MAX. */
#define SAVE_LABEL_MAX 64
void save_room_label(const SaveRoom *s, char *buf);

#endif
