/* Archipelago Menu core (see apmenu.h): hold L3 to open it, tap L3 for the pages' l3_tap (the
 * minimap's show/hide). The main page lists the AP_PAGE() pages in order; the world is frozen
 * while the menu is open, as for a message box. Input comes from the game's own pad block (the
 * frozen world ignores it). Hook: jal Obj_UpdateAll @ 0x439F00 in GameplayFrame case 0, which
 * also runs on frozen frames. */
#include "apmenu.h"

#define MAIN_TITLE "Archipelago Menu: " AP_MENU_VERSION
#define HOLD_FRAMES 180         /* L3 held this long opens the menu */
#define PAGE_DEPTH 4

#define MENU_LAYER 1
#define MENU_X (-236)           /* left edge of the screen, 20 px in */
#define MENU_Y (-130)           /* first row; the title is a line above */
#define LINE_HEIGHT 20          /* the font is about 18 px tall at scale 0x100 */
/* rows drawn at once; longer pages scroll. 14 puts the help line at y 158, its bottom near 176,
 * inside the 224 half-height with room for TV overscan */
#define VISIBLE_ROWS 14
#define COLOUR_TITLE RGBA(0x80, 0x80, 0x80, 0x80)
#define COLOUR_ITEM  RGBA(0x70, 0x70, 0x70, 0x80)
#define COLOUR_SEL   RGBA(0x80, 0x80, 0x30, 0x80)
#define COLOUR_HELP  RGBA(0x60, 0x60, 0x60, 0x80)

/* the AP_PAGE() entries, sorted by order (game.ld) */
extern const ApPage *const __submenus_start[];
extern const ApPage *const __submenus_end[];
#define PAGE_COUNT ((int)(__submenus_end - __submenus_start))

static const TextStyle menu_style = {8, 0x80808080, 0, 0x100, 0x100, 0};

/* state lives in .bss, which the pnach never writes */
static int menu_open;
static const ApPage *page;      /* 0 = main page */
static int selected;
static int top;                 /* first row drawn (scrolling) */
static int l3_frames;           /* frames L3 has been held */
static int l3_used;             /* this L3 press already opened/closed the menu */

int apmenu_is_open(void) { return menu_open; }

int apmenu_game_busy(void)
{
    u8 *box = MsgBox_Get();

    return IsWorldFrozen() || (*(volatile u8 *)0x00B36750 & 1)
        || (box && *(volatile int *)(box + MSGBOX_OPEN_FLAG));
}

static void set_open(int open)
{
    if (open == menu_open)
        return;
    menu_open = open;
    if (open) {
        World_Freeze(0);
        World_SetPausedBit(1);
        page = 0;
        selected = 0;
        top = 0;
    } else {
        World_Unfreeze();
        World_SetPausedBit(0);
    }
}

void apmenu_close(void) { set_open(0); }

/* ---- pages ---- */

static int row_count(void)
{
    if (!page)
        return PAGE_COUNT;
    return page->row_count ? page->row_count() : page->rows;
}

static void row_text(int row, char *out)
{
    if (page)
        page->row_text(row, out);
    else
        GameSprintf(out, "%s", __submenus_start[row]->title);
}

static void help_text(char *out)
{
    if (!page)
        GameSprintf(out, "Cross select  Triangle close");
    else if (page->help)
        page->help(selected, out);
    else
        GameSprintf(out, "Cross OK  Triangle back");
}

/* keeps the selected row inside the VISIBLE_ROWS window */
static void scroll_to_selected(int rows)
{
    if (selected < top)
        top = selected;
    if (selected >= top + VISIBLE_ROWS)
        top = selected - VISIBLE_ROWS + 1;
    if (top > rows - VISIBLE_ROWS)
        top = rows - VISIBLE_ROWS;
    if (top < 0)
        top = 0;
}

static void draw_menu(void)
{
    char text[APMENU_ROW_TEXT], line[APMENU_ROW_TEXT + 4];
    const char *title = page ? page->title : MAIN_TITLE;
    int rows = row_count(), shown, i;

    if (selected >= rows)
        selected = rows > 0 ? rows - 1 : 0;
    scroll_to_selected(rows);
    shown = rows < VISIBLE_ROWS ? rows : VISIBLE_ROWS;

    /* a page that scrolls says which rows are showing: "Title  1-14 of 19" */
    if (rows > VISIBLE_ROWS)
        GameSprintf(line, "%s  %d-%d of %d", title, top + 1, top + shown, rows);
    else
        GameSprintf(line, "%s", title);
    DrawText(line, &menu_style, MENU_X, MENU_Y - LINE_HEIGHT, MENU_LAYER, COLOUR_TITLE);
    for (i = 0; i < shown; i++) {
        int row = top + i;

        row_text(row, text);
        GameSprintf(line, "%s%s", row == selected ? "> " : "  ", text);
        DrawText(line, &menu_style, MENU_X + 4, MENU_Y + 4 + i * LINE_HEIGHT, MENU_LAYER,
                 row == selected ? COLOUR_SEL : COLOUR_ITEM);
    }
    help_text(line);
    DrawText(line, &menu_style, MENU_X, MENU_Y + 8 + shown * LINE_HEIGHT, MENU_LAYER,
             COLOUR_HELP);
}

static void open_page(const ApPage *sub)
{
    page = sub;
    selected = 0;
    top = 0;
    if (sub->open)
        sub->open();
}

/* back to the main page, with the page we came from selected */
static void back(void)
{
    int i;

    for (i = 0; i < PAGE_COUNT; i++)
        if (__submenus_start[i] == page)
            selected = i;
    page = 0;
    top = 0;
}

static void menu_input(u16 pressed)
{
    int rows = row_count();

    if (rows <= 0)
        rows = 1;
    if (selected >= rows)
        selected = rows - 1;
    if (pressed & BTN_UP)
        selected = (selected + rows - 1) % rows;
    else if (pressed & BTN_DOWN)
        selected = (selected + 1) % rows;
    else if (pressed & BTN_CROSS) {
        if (!page)
            open_page(__submenus_start[selected]);
        else if (page->confirm)
            page->confirm(selected);
    } else if (pressed & (BTN_TRIANGLE | BTN_CIRCLE)) {
        if (page)
            back();
        else
            set_open(0);
    } else if (page && page->adjust && (pressed & (BTN_LEFT | BTN_RIGHT))) {
        page->adjust(selected, pressed & BTN_LEFT ? -1 : 1);
    }
}

/* L3: held HOLD_FRAMES opens the menu; a tap closes it, or goes to the pages' l3_tap */
static void l3_tick(u16 held)
{
    int i;

    if (held & BTN_L3) {
        l3_frames++;
        if (l3_frames == HOLD_FRAMES && !menu_open && !l3_used && !apmenu_game_busy()) {
            set_open(1);
            l3_used = 1;
        }
        return;
    }
    if (l3_frames > 0 && l3_frames < HOLD_FRAMES && !l3_used) {
        if (menu_open) {
            set_open(0);
        } else if (!apmenu_game_busy()) {
            for (i = 0; i < PAGE_COUNT; i++)
                if (__submenus_start[i]->l3_tap)
                    __submenus_start[i]->l3_tap();
        }
    }
    l3_frames = 0;
    l3_used = 0;
}

/* replaces "jal Obj_UpdateAll" @ 0x439F00 (runs on frozen frames too) */
void apmenu_hook(void)
{
    u16 held = *(volatile u16 *)(PAD0_STRUCT + 2);
    u16 pressed = *(volatile u16 *)(PAD0_STRUCT + 4);
    int i;

    Obj_UpdateAll();
    l3_tick(held);
    if (menu_open && pressed)
        menu_input(pressed);
    for (i = 0; i < PAGE_COUNT; i++)
        if (__submenus_start[i]->frame)
            __submenus_start[i]->frame();
    if (menu_open)
        draw_menu();
}
