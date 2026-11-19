/* The save rooms (savewarps.c), shared by the Savewarps page and the Savewarp Ticket (ticket.c). */
#ifndef SAVEWARPS_H
#define SAVEWARPS_H

#include "game.h"

typedef struct {
    u8 stage, room;
    u8 number;      /* "Save n" within its area */
    const char *area;
} SaveRoom;

extern const SaveRoom save_rooms[];
extern const int save_room_count;

int save_room_visited(const SaveRoom *s);   /* Leon has been in it (the pause map's flag) */
int save_room_here(const SaveRoom *s);      /* Leon is in it now */
int in_save_room(void);                     /* Leon is in one of them now */

#endif
