/* Quality-of-life options (qol.c), set by the client in AP_STATUS->qol. */
#ifndef QOL_H
#define QOL_H

#include "game.h"

#define QOL_WOLFS_FOOT 0x1      /* Wolf's Foot drains MP at half the rate */

void qol_frame(void);           /* every frame, from frame_end_hook */

#endif
