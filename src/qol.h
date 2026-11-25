/* Quality-of-life options (qol.c), set by the client in AP_STATUS->qol. */
#ifndef QOL_H
#define QOL_H

#include "game.h"

#define QOL_WOLFS_FOOT 0x1      /* Wolf's Foot drains MP at QOL_WOLFS_FOOT_PCT(qol) percent of the
                                   normal rate (0 = no drain); clear: normal */
#define QOL_WOLFS_FOOT_SHIFT 8
#define QOL_WOLFS_FOOT_PCT(qol) (((qol) >> QOL_WOLFS_FOOT_SHIFT) & 0xFF)

void qol_frame(void);           /* every frame, from frame_end_hook */

#endif
