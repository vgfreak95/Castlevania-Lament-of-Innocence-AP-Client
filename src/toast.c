/* Received-item notices (toast.h): "Received" in green, then the item name (and
 * " from <sender>" when it fits) in the HUD's white, right-aligned in the
 * bottom-right corner (top right when the minimap is there, toast.h). Each line
 * stays TOAST_HOLD frames and fades out over TOAST_FADE; the oldest is on top. Lines are measured once when queued
 * (Text_Measure): a line wider than TOAST_MAX_W drops its sender, and if it is
 * still too wide it is drawn smaller (both axes, so it keeps its shape). */
#include "toast.h"

/* the pickups patch is tight below its mailbox (0xFC000): build this file for
 * size */
#pragma GCC optimize("Os")

#define TOAST_SCALE 0xB0 /* ~69% of the HUD text ("Checks left" HUD text base is 0x100) */
#define TOAST_HOLD 140   /* frames at full alpha (about a second) */
#define TOAST_FADE                                                             \
  32 /* then fades out over this many (power of two: a shift) */
#define TOAST_LINE_H                                                           \
  ((TOAST_SCALE * 20) >> 8) /* the font is ~18 px tall at 0x100 */
#define TOAST_RIGHT                                                            \
  248 /* right edge: screen half-width 256 minus the minimap's margin */
#define TOAST_TOP (-216)   /* top-right stack: first line's y (224 - the 8 margin) */
#define TOAST_BOTTOM 216   /* bottom-right stack: bottom edge of the last line */
#define TOAST_MAX_W 280 /* widest line, so it stays clear of the HP/MP bars */
#define TOAST_LAYER 1
#define TOAST_ALPHA 8 /* text[] index of the alpha's first hex digit */
#define TOAST_PREFIX "^C40ff4080Received^c "

static __attribute__((noinline)) int measure(const char *text, int scale) {
  TextStyle st = {8, 0x80808080, 0, scale, scale, 0};
  int w = 0, h;

  Text_Measure(text, &st, 0, 0, &w, &h);
  return w;
}

int toast_full(void) { return TOAST->count >= TOAST_LINES; }

int toast_push(const char *name, const char *sender, int gold) {
  ToastArea *t = TOAST;
  ToastLine *l;
  int w, scale = TOAST_SCALE;

  if (toast_full())
    return 0;
  l = &t->line[(t->first + t->count) % TOAST_LINES];
  if (gold) {
    GameSprintf(l->text, TOAST_PREFIX "%s: no room, $%d", name, gold);
  } else {
    GameSprintf(l->text, TOAST_PREFIX "%s from %s", name, sender);
    if (measure(l->text, scale) > TOAST_MAX_W)
      GameSprintf(l->text, TOAST_PREFIX "%s",
                  name); /* too long: drop the sender */
  }
  w = measure(l->text, scale);
  if (w > TOAST_MAX_W) {
    scale = scale * TOAST_MAX_W / w;
    w = measure(l->text, scale);
  }
  l->age = 0;
  l->width = w;
  l->scale = scale;
  t->count++;
  return 1;
}

void toast_frame(void) {
  ToastArea *t = TOAST;
  int top = t->use_top, y, i, alpha, d;

  t->use_top = 0; /* minimap.c sets it again on the next frame */
  if (t->magic != TOAST_MAGIC || t->count > TOAST_LINES) {
    t->first = t->count = 0;
    t->magic = TOAST_MAGIC;
  }
  y = top ? TOAST_TOP : TOAST_BOTTOM - (int)t->count * TOAST_LINE_H;
  if (IsWorldFrozen() || ITEM_RING_OPEN())
    return; /* hidden, and not aging, like "Checks left" */
  for (i = 0; i < (int)t->count; i++) {
    ToastLine *l = &t->line[(t->first + i) % TOAST_LINES];
    TextStyle st = {8, 0x80808080, 0, l->scale, l->scale, 0};

    alpha = 0x80 - ((l->age - TOAST_HOLD) << 7) / TOAST_FADE;
    if (alpha > 0x80)
      alpha = 0x80;
    if (alpha < 0)
      alpha = 0;
    l->age++;
    d = alpha & 15;
    l->text[TOAST_ALPHA] = '0' + (alpha >> 4); /* 0-8 */
    l->text[TOAST_ALPHA + 1] = d < 10 ? '0' + d : 'a' - 10 + d;
    /* x: right-aligned; the line was fitted to TOAST_MAX_W, so it stays on
     * screen */
    DrawText(l->text, &st, TOAST_RIGHT - l->width, y, TOAST_LAYER,
             RGBA(0x80, 0x80, 0x80, alpha));
    y += TOAST_LINE_H;
  }
  if (t->count &&
      t->line[t->first % TOAST_LINES].age >= TOAST_HOLD + TOAST_FADE) {
    t->first++; /* lines age together: at most the oldest expires per frame */
    t->count--;
  }
}
