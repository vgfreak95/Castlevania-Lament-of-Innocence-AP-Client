/* Archipelago Menu SDK (part of the Minimap patch; a cut-down port of the Debug-Tools menu SDK).
 * The core (apmenu.c) runs the menu: hold L3 to open it, the main page, input and drawing. Each
 * page fills in an ApPage and registers it with AP_PAGE(); the main page lists them in order.
 *
 *   #include "apmenu.h"
 *
 *   static void hello_text(int row, char *out) { GameSprintf(out, "Say hello"); }
 *   static void hello_confirm(int row)         { GamePrintf("hello\n"); }
 *
 *   AP_PAGE(hello_page, 050) = {
 *       .title    = "Hello",
 *       .rows     = 1,
 *       .row_text = hello_text,
 *       .confirm  = hello_confirm,
 *   };
 *
 * The world is frozen while the menu is open. Controls: Up/Down select, Cross open/confirm,
 * Left/Right adjust, Triangle or Circle back (closes on the main page), L3 close.
 * State belongs in .bss (static variables without an initialiser): the pnach rewrites the
 * initialised data every frame, so `static int x = 1;` would snap back to 1. */
#ifndef APMENU_H
#define APMENU_H

#include "game.h"

#define AP_MENU_VERSION "0.5.0"
#define APMENU_ROW_TEXT 64   /* size of the `out` buffers; GameSprintf doesn't check */

typedef struct ApPage {
    const char *title;                      /* main-page row and page title */
    int rows;                               /* rows on the page, unless row_count is set */
    int (*row_count)(void);                 /* rows that change at run time (at least 1) */
    void (*row_text)(int row, char *out);   /* one row's text */
    void (*confirm)(int row);               /* Cross on a row */
    void (*adjust)(int row, int delta);     /* Left/Right: delta -1/+1 */
    void (*help)(int row, char *out);       /* bottom line; default "Cross OK  Triangle back" */
    void (*open)(void);                     /* the page was opened from the main page */

    /* always, menu open or closed (runs on frozen frames too) */
    void (*frame)(void);
    void (*l3_tap)(void);                   /* L3 tapped while the menu is closed */
} ApPage;

/* AP_PAGE(name, order) = { ... };  registers a page. `order` (three digits) sets its place on
 * the main page, lowest first: 010 Minimap Options. Uses the .submenus.* sections
 * that game.ld collects. */
#define AP_PAGE(name, order)                                                              \
    static const ApPage name;                                                             \
    static const ApPage *const name##_entry                                               \
        __attribute__((used, section(".submenus." #order))) = &name;                      \
    static const ApPage name

int apmenu_is_open(void);
void apmenu_close(void);   /* unfreezes the world */

/* nonzero while the game is busy (frozen, paused or showing a message box): the menu doesn't
 * open and the minimap hides */
int apmenu_game_busy(void);

#endif
