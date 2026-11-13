/* Minimap: the visited rooms of Leon's floor around him, in a corner of the screen.
 * - Room shapes come from the pause map's own model (game.h "area map"): for every piece, the
 *   vertices of its fill and outline parts, taken in the room's frame, give an oriented box. All
 *   boxes are computed once when the area's map file changes.
 * - Visited = bit 0 of the room's state word (the pause map's own flag). Save rooms (piece flag
 *   0x2, drawn red on the pause map) are red; rooms whose AP pickup locations are all collected
 *   are green; rooms with some left get an orange marker (ap_locations.h, as "Pickups left").
 * - Room transitions: each room's door records, remembered in map space while Leon is in it.
 * - Leon's dot uses the pause map marker's formula (0x6C3EB8).
 * - Drawing: untextured type 4 sprites (game.h "2D primitives"); rotated rooms are filled from
 *   ROW_H-pixel rows, since the 4-vertex primitives don't work as a plain object.
 * - Controls: tap L3 to show/hide; hold L3 to open the settings menu (the world is frozen while it
 *   is open, as for a message box). Settings last until the console resets.
 * Hooks: jal Player_UpdateStep @ 0x439EC8 (GameplayFrame case 0, skipped while the world is
 * frozen) draws the minimap; jal Obj_UpdateAll @ 0x439F00 (also runs on frozen frames) reads L3
 * and runs the menu. */
#include "game.h"
#include "ap_locations.h"

#define LAYER       1          /* the HUD text's layer */
#define GS_Z        65000      /* as the screen fade */
#define MAX_SPRITES 220        /* per frame, so the minimap can't drain the game's prim pool */
#define ROW_H       2.0f       /* row height for rotated rooms */
#define DOT_R       2.0f
#define MARK_R      1.5f
#define DOOR_R      1.5f
#define SCREEN_W2   256.0f     /* half screen; coordinates are screen-centre relative, y down */
#define SCREEN_H2   224.0f
#define MARGIN      8.0f
#define HOLD_FRAMES 45         /* L3 held this long opens the menu */

/* base colours, alpha scaled by the opacity setting: [0] elsewhere, [1] Leon is in the room */
static const int panel_rgba[4] = {0x00, 0x00, 0x00, 0x40};
static const int room_rgba[2][4] = {{0x30, 0x48, 0x70, 0x60}, {0x50, 0x78, 0x80, 0x70}};
static const int save_rgba[2][4] = {{0x70, 0x18, 0x18, 0x60}, {0x80, 0x48, 0x48, 0x70}};
static const int clear_rgba[2][4] = {{0x20, 0x60, 0x28, 0x60}, {0x48, 0x80, 0x50, 0x70}};
static const int dot_rgba[4] = {0x80, 0x80, 0x30, 0x80};
static const int mark_rgba[4] = {0x80, 0x50, 0x10, 0x80};
static const int door_rgba[4] = {0x80, 0x80, 0x80, 0x80};

static const TextStyle text_style = {8, 0x80808080, 0, 0x100, 0x100, 0};

/* ---- settings (.bss only: the pnach rewrites initialised data every frame) ---- */

static const float zoom_scales[] = {0.03f, 0.045f, 0.06f, 0.09f, 0.13f};
static const float panel_w[] = {80.0f, 112.0f, 150.0f};
static const float panel_h[] = {66.0f, 92.0f, 124.0f};
static const char *const size_names[] = {"Small", "Medium", "Large"};
static const char *const corner_names[] = {"Top right", "Top left", "Bottom right", "Bottom left"};
static const int opacity_pct[] = {40, 60, 80, 100, 125};
#define N_ZOOM    5
#define N_SIZE    3
#define N_CORNER  4
#define N_OPACITY 5

static int settings_ready;
static int set_hidden;         /* 1 = minimap hidden (tap L3) */
static int set_zoom, set_size, set_corner, set_opacity;
static int set_no_doors, set_no_marks, set_no_green;   /* 1 = that feature off */

static void settings_init(void)
{
    if (settings_ready)
        return;
    set_zoom = 2;
    set_size = 1;
    set_corner = 0;
    set_opacity = 3;
    settings_ready = 1;
}

/* panel and clip rectangle for this frame */
static float panel_x0, panel_y0, panel_x1, panel_y1, panel_cx, panel_cy, map_scale;
static float clip_x0, clip_y0, clip_x1, clip_y1;

static void layout(void)
{
    float w = panel_w[set_size], h = panel_h[set_size];
    int right = set_corner == 0 || set_corner == 2, bottom = set_corner >= 2;

    panel_x1 = right ? SCREEN_W2 - MARGIN : -SCREEN_W2 + MARGIN + w;
    panel_x0 = panel_x1 - w;
    panel_y1 = bottom ? SCREEN_H2 - MARGIN : -SCREEN_H2 + MARGIN + h;
    panel_y0 = panel_y1 - h;
    panel_cx = (panel_x0 + panel_x1) * 0.5f;
    panel_cy = (panel_y0 + panel_y1) * 0.5f;
    map_scale = zoom_scales[set_zoom];
}

static void clip_panel(void)
{
    clip_x0 = panel_x0;
    clip_y0 = panel_y0;
    clip_x1 = panel_x1;
    clip_y1 = panel_y1;
}

/* ---- math (no libm) ---- */

#define PI 3.14159265f

static float sin_approx(float x)
{
    float x2;
    while (x > PI)
        x -= 2.0f * PI;
    while (x < -PI)
        x += 2.0f * PI;
    x2 = x * x;
    return x * (1.0f - x2 / 6.0f * (1.0f - x2 / 20.0f * (1.0f - x2 / 42.0f * (1.0f - x2 / 72.0f))));
}

static float cos_approx(float x)
{
    return sin_approx(x + PI * 0.5f);
}

/* ---- primitives ---- */

static u8 *frame_regs;          /* this pass's shared GS register list */
static int sprites_left;

static int gs_xy(float v)
{
    return (int)((v + 2048.0f) * 16.0f);
}

/* TEST and ALPHA as the screen fade: no Z writes, Z always, (Cs - Cd) * As + Cd */
static int begin_frame(void)
{
    frame_regs = Prim_Alloc(0x60);
    if (!frame_regs)
        return 0;
    GsRegs_Init(frame_regs);
    GsRegs_Set(frame_regs, GS_REG_TEST_1, 0x31001);
    GsRegs_Set(frame_regs, GS_REG_ALPHA_1, 0x44);
    sprites_left = MAX_SPRITES;
    return 1;
}

/* untextured rectangle, clipped; alpha scaled by the opacity setting unless `solid` */
static void draw_rect_a(float x0, float y0, float x1, float y1, const int *rgba, int solid)
{
    u8 *obj;
    int *v, col[4];

    if (x0 < clip_x0) x0 = clip_x0;
    if (y0 < clip_y0) y0 = clip_y0;
    if (x1 > clip_x1) x1 = clip_x1;
    if (y1 > clip_y1) y1 = clip_y1;
    if (x1 <= x0 || y1 <= y0 || sprites_left <= 0)
        return;
    obj = Prim_Alloc(0x90);
    if (!obj) {
        sprites_left = 0;
        return;
    }
    sprites_left--;
    col[0] = rgba[0];
    col[1] = rgba[1];
    col[2] = rgba[2];
    col[3] = solid ? rgba[3] : rgba[3] * opacity_pct[set_opacity] / 100;
    if (col[3] > 0x80)
        col[3] = 0x80;
    Prim_Init(obj, 4);
    Prim_SetRegs(obj, frame_regs);
    Prim_SetFlags(obj, 1, 0, 1, 0);            /* alpha blending on */
    Prim_SetVertexCount(obj, 2);               /* 2-vertex sprite */
    obj[PRIM_TME_BYTE] &= ~PRIM_TME_BIT;       /* untextured */
    Prim_SetColour(obj, col);
    v = (int *)(obj + PRIM_VERTS);
    v[4] = gs_xy(x0);
    v[5] = gs_xy(y0);
    v[6] = GS_Z;
    v[0xC] = gs_xy(x1);
    v[0xD] = gs_xy(y1);
    v[0xE] = GS_Z;
    Prim_SubmitLayer(obj, LAYER);
}

static void draw_rect(float x0, float y0, float x1, float y1, const int *rgba)
{
    draw_rect_a(x0, y0, x1, y1, rgba, 0);
}

/* filled convex quad, corners in order around the edge, from ROW_H-pixel rows */
static void draw_quad(const float *xy, const int *rgba)
{
    float ymin = xy[1], ymax = xy[1], y;
    int i;

    for (i = 1; i < 4; i++) {
        if (xy[i * 2 + 1] < ymin) ymin = xy[i * 2 + 1];
        if (xy[i * 2 + 1] > ymax) ymax = xy[i * 2 + 1];
    }
    if (ymin < clip_y0) ymin = clip_y0;
    if (ymax > clip_y1) ymax = clip_y1;
    for (y = ymin; y < ymax; y += ROW_H) {
        float yc = y + ROW_H * 0.5f, x0 = 1e9f, x1 = -1e9f;

        for (i = 0; i < 4; i++) {
            float ax = xy[i * 2], ay = xy[i * 2 + 1];
            float bx = xy[((i + 1) & 3) * 2], by = xy[((i + 1) & 3) * 2 + 1];

            if ((ay <= yc && by > yc) || (by <= yc && ay > yc)) {
                float x = ax + (yc - ay) * (bx - ax) / (by - ay);
                if (x < x0) x0 = x;
                if (x > x1) x1 = x;
            }
        }
        if (x1 > x0)
            draw_rect(x0, y, x1, y + ROW_H, rgba);
    }
}

/* ---- area cache: one oriented box per map piece ---- */
#define MAX_PIECES 192
#define NO_PIECE   0xFF

typedef struct {
    u8 *piece;
    float c, s;                    /* cos/sin of the piece's yaw */
    float x0, x1, z0, z1;          /* box in the room's frame */
    int ok;
} RoomBox;

static RoomBox boxes[MAX_PIECES];
static int box_count;
static u8 *cached_file;
static u8 part_owner[256];

static u8 *map_model(u8 *file)
{
    u8 *p;
    int count, i;

    count = *(int *)(file + 4);
    if (count <= 0)
        return 0;
    p = *(u8 **)(file + 0x30 + 4 * (count - 1)) + 0x60;
    p = (u8 *)(((u32)p + 15) & ~15u);
    for (i = 0; i < 8; i++, p += 16)
        if ((*(u32 *)p & 0xFFFF0000u) == 0xFFFF0000u)
            return p;
    return 0;
}

static void add_vertex(RoomBox *b, float mx, float mz)
{
    const float *pos = (const float *)(b->piece + PIECE_POS);
    float dx = mx - pos[0], dz = mz - pos[2];
    float lx = b->c * dx - b->s * dz, lz = b->s * dx + b->c * dz;   /* RotY(-yaw) */

    if (!b->ok) {
        b->x0 = b->x1 = lx;
        b->z0 = b->z1 = lz;
        b->ok = 1;
        return;
    }
    if (lx < b->x0) b->x0 = lx;
    if (lx > b->x1) b->x1 = lx;
    if (lz < b->z0) b->z0 = lz;
    if (lz > b->z1) b->z1 = lz;
}

static void build_cache(u8 *file)
{
    u8 *model, *mesh;
    int i, k, n;

    cached_file = file;
    box_count = 0;
    for (i = 0; i < 256; i++)
        part_owner[i] = NO_PIECE;
    if (!file || *(int *)file != 1)
        return;
    n = *(int *)(file + 4);
    if (n > MAX_PIECES)
        n = MAX_PIECES;
    for (i = 0; i < n; i++) {
        RoomBox *b = &boxes[i];
        u8 *piece = *(u8 **)(file + 0x30 + 4 * i);
        const u16 *counts = (const u16 *)(piece + PIECE_COUNTS);
        float yaw = ((const float *)(piece + PIECE_POS))[3];

        b->piece = piece;
        b->c = cos_approx(yaw);
        b->s = sin_approx(yaw);
        b->ok = 0;
        for (k = 0; k < counts[0] && k < 4; k++)
            part_owner[piece[PIECE_FILL + k]] = i;
        for (k = 0; k < counts[1] && k < 4; k++)
            part_owner[piece[PIECE_OUTLINE + k]] = i;
    }
    box_count = n;

    model = map_model(file);
    if (!model)
        return;
    n = *(int *)(model + MODEL_MESH_COUNT);
    mesh = model + *(int *)(model + MODEL_MESH_OFS);
    for (i = 0; i < n; i++) {
        u32 size = *(u32 *)mesh, q;
        int owner;

        if (size < 0x50 || size > 0x10000)
            break;
        owner = part_owner[mesh[MESH_PART]];
        if (owner != NO_PIECE) {
            for (q = 0x50; q + 4 <= size; q += 4) {
                u32 w = *(u32 *)(mesh + q);
                const int *v;
                int num;

                if ((w >> 24) != VIF_UNPACK_V3_32)
                    continue;
                num = (w >> 16) & 0xFF;
                v = (const int *)(mesh + q + 4);
                for (k = 0; k < num; k++, v += 3)
                    add_vertex(&boxes[owner], (float)v[0] / 16.0f, -(float)v[2] / 16.0f);
                q += 12 * num;
            }
        }
        mesh += size;
    }
    GamePrintf("[minimap] map file %d: %d pieces cached\n", *(volatile int *)0x00B90970, box_count);
}

/* ---- rooms ---- */

static int room_visited(const u8 *piece)
{
    int key = GetRoomKey(piece[0], piece[PIECE_ROOM]);
    u32 *table = ROOM_STATE;

    if (!table || key < 0 || key >= ROOM_STATE_COUNT)
        return 0;
    return table[key * 3] & 1;
}

/* AP pickup locations in this room: how many, and how many still have their collected flag clear */
static void room_pickups(const u8 *piece, int *total, int *left)
{
    int key = GetRoomKey(piece[0], piece[PIECE_ROOM]);
    int i;

    *total = 0;
    *left = 0;
    for (i = 0; i < AP_PICKUP_COUNT; i++) {
        int k = ap_pickup_keys[i];
        if (k / 64 != key)
            continue;
        (*total)++;
        if (!GetRoomItemFlag(key, k % 64))
            (*left)++;
    }
}

static void local_to_map(const RoomBox *b, float lx, float lz, float *mx, float *mz)
{
    const float *pos = (const float *)(b->piece + PIECE_POS);

    *mx = pos[0] + b->c * lx + b->s * lz;
    *mz = pos[2] - b->s * lx + b->c * lz;
}

/* world -> map in the room `piece` belongs to, as the pause map marker (0x6C3EB8) */
static void world_to_map(const u8 *piece, float wx, float wz, float *mx, float *mz)
{
    const float *pos = (const float *)(piece + PIECE_POS);
    const float *scale = (const float *)(piece + PIECE_SCALE);
    float c = cos_approx(pos[3]), s = sin_approx(pos[3]);
    float x = wx * 0.1f, z = wz * 0.1f;

    *mx = pos[0] + scale[0] * (c * x + s * z);
    *mz = pos[2] + scale[2] * (-s * x + c * z);
}

/* ---- room transitions ----
 * Door records exist only for the loaded room (ROOMDATA object list 0, game.h "rooms"), so each
 * room's doors are remembered in map space when Leon is in it, until the console resets. */
#define MAX_ROOMS  416
#define MAX_DOORS  8

typedef struct {
    short x, z;                    /* map units */
    signed char floor;
    u8 pad;
} DoorMark;

static DoorMark doors[MAX_ROOMS][MAX_DOORS];
static u8 door_count[MAX_ROOMS];   /* doors + 1 once the room was read, 0 = not yet */

static void read_doors(const u8 *here, int key)
{
    u8 *rd = ROOMDATA, *list;
    int count, i, n = 0;

    if (!rd || key < 0 || key >= MAX_ROOMS || door_count[key])
        return;
    list = *(u8 **)(*(u8 **)(rd + ROOMDATA_OBJLISTS) + 4);   /* object list 0 */
    if (!list)
        return;
    count = *(int *)(list + OBJLIST_COUNT);
    for (i = 0; i < count && n < MAX_DOORS; i++) {
        const u8 *rec = list + 0x10 + 0x80 * i;
        const float *wpos = (const float *)rec;
        float mx, mz;

        if (*(const short *)(rec + DOOR_DEST_STAGE) < 0 || *(const short *)(rec + DOOR_DEST_ROOM) < 0)
            continue;
        world_to_map(here, wpos[0], wpos[2], &mx, &mz);
        doors[key][n].x = (short)mx;
        doors[key][n].z = (short)mz;
        doors[key][n].floor = (signed char)here[PIECE_FLOOR];
        n++;
    }
    door_count[key] = n + 1;
}

/* ---- drawing the minimap ---- */

static int game_busy(void)
{
    u8 *box = MsgBox_Get();
    return IsWorldFrozen() || (*(volatile u8 *)0x00B36750 & 1) ||
           (box && *(volatile int *)(box + MSGBOX_OPEN_FLAG));
}

static void map_to_screen(float mx, float mz, float cx, float cz, float *sx, float *sy)
{
    *sx = panel_cx + (mx - cx) * map_scale;
    *sy = panel_cy + (mz - cz) * map_scale;
}

/* draws the minimap; `preview` = called from the menu (world frozen by us) */
static void minimap_draw(int preview)
{
    u8 *file = MAP_FILE, *here;
    float cx, cz, sx, sy;
    int floor, i, j;

    settings_init();
    if (!file || (!preview && (set_hidden || game_busy())))
        return;
    if (file != cached_file)
        build_cache(file);
    here = Map_GetCurrentPiece();
    if (!here || !box_count)
        return;
    read_doors(here, GetRoomKey(CUR_STAGE, CUR_ROOM));
    if (!begin_frame())
        return;

    layout();
    clip_panel();
    world_to_map(here, PLAYER_POS[0], PLAYER_POS[2], &cx, &cz);
    floor = (signed char)here[PIECE_FLOOR];
    draw_rect(panel_x0, panel_y0, panel_x1, panel_y1, panel_rgba);

    for (i = 0; i < box_count; i++) {
        const RoomBox *b = &boxes[i];
        const float lx[4] = {b->x0, b->x1, b->x1, b->x0};
        const float lz[4] = {b->z0, b->z0, b->z1, b->z1};
        const int (*rgba)[4];
        float q[8], mx, mz;
        int is_here = b->piece == here;
        int total, left;

        if (!b->ok || (signed char)b->piece[PIECE_FLOOR] != floor)
            continue;
        if (!is_here && !room_visited(b->piece))
            continue;
        for (j = 0; j < 4; j++) {
            local_to_map(b, lx[j], lz[j], &mx, &mz);
            map_to_screen(mx, mz, cx, cz, &q[j * 2], &q[j * 2 + 1]);
        }
        /* save rooms red (they have no pickups); rooms whose AP pickups are all taken green */
        room_pickups(b->piece, &total, &left);
        if (*(const u16 *)(b->piece + PIECE_FLAGS) & PIECE_FLAG_SAVE)
            rgba = save_rgba;
        else if (total && !left && !set_no_green)
            rgba = clear_rgba;
        else
            rgba = room_rgba;
        draw_quad(q, rgba[is_here]);
        if (left && !set_no_marks) {
            local_to_map(b, (b->x0 + b->x1) * 0.5f, (b->z0 + b->z1) * 0.5f, &mx, &mz);
            map_to_screen(mx, mz, cx, cz, &sx, &sy);
            draw_rect(sx - MARK_R, sy - MARK_R, sx + MARK_R, sy + MARK_R, mark_rgba);
        }
    }

    /* room transitions, on top of the rooms (overlaps between neighbours are fine for now) */
    for (i = 0; i < box_count && !set_no_doors; i++) {
        const u8 *piece = boxes[i].piece;
        int key, n;

        if (!boxes[i].ok || (signed char)piece[PIECE_FLOOR] != floor)
            continue;
        if (piece != here && !room_visited(piece))
            continue;
        key = GetRoomKey(piece[0], piece[PIECE_ROOM]);
        if (key < 0 || key >= MAX_ROOMS || !door_count[key])
            continue;
        for (n = 0; n < door_count[key] - 1; n++) {
            const DoorMark *d = &doors[key][n];

            if (d->floor != floor)
                continue;
            map_to_screen(d->x, d->z, cx, cz, &sx, &sy);
            draw_rect(sx - DOOR_R, sy - DOOR_R, sx + DOOR_R, sy + DOOR_R, door_rgba);
        }
    }
    draw_rect(panel_cx - DOT_R, panel_cy - DOT_R, panel_cx + DOT_R, panel_cy + DOT_R, dot_rgba);
}

/* ---- L3 and the settings menu ---- */

enum { M_SHOW, M_ZOOM, M_SIZE, M_CORNER, M_OPACITY, M_DOORS, M_MARKS, M_GREEN, M_CLOSE, M_COUNT };

static int menu_open, menu_sel;
static int l3_frames;              /* frames L3 has been held */
static int l3_used;                /* this L3 press already opened/closed the menu */

static void menu_set_open(int open)
{
    if (open == menu_open)
        return;
    menu_open = open;
    if (open) {
        World_Freeze(0);
        World_SetPausedBit(1);
        menu_sel = 0;
    } else {
        World_Unfreeze();
        World_SetPausedBit(0);
    }
}

static void step(int *value, int count, int dir)
{
    *value = (*value + dir + count) % count;
}

static void menu_change(int dir)
{
    switch (menu_sel) {
    case M_SHOW:    set_hidden = !set_hidden; break;
    case M_ZOOM:    step(&set_zoom, N_ZOOM, dir); break;
    case M_SIZE:    step(&set_size, N_SIZE, dir); break;
    case M_CORNER:  step(&set_corner, N_CORNER, dir); break;
    case M_OPACITY: step(&set_opacity, N_OPACITY, dir); break;
    case M_DOORS:   set_no_doors = !set_no_doors; break;
    case M_MARKS:   set_no_marks = !set_no_marks; break;
    case M_GREEN:   set_no_green = !set_no_green; break;
    }
}

static const char *on_off(int off)
{
    return off ? "Off" : "On";
}

#define MENU_LINE_H 20     /* the font is about 18 px tall at scale 0x100 */

#define MENU_X (-236)      /* left edge of the screen, 20 px in */

static void menu_draw(void)
{
    char text[48];
    int i, y0 = -110;

    DrawText("Minimap", &text_style, MENU_X, y0 - 20, LAYER, RGBA(0x80, 0x80, 0x80, 0x80));
    for (i = 0; i < M_COUNT; i++) {
        switch (i) {
        case M_SHOW:    GameSprintf(text, "Minimap: %s", on_off(set_hidden)); break;
        case M_ZOOM:    GameSprintf(text, "Zoom: %d / %d", set_zoom + 1, N_ZOOM); break;
        case M_SIZE:    GameSprintf(text, "Size: %s", size_names[set_size]); break;
        case M_CORNER:  GameSprintf(text, "Corner: %s", corner_names[set_corner]); break;
        case M_OPACITY: GameSprintf(text, "Opacity: %d%%", opacity_pct[set_opacity]); break;
        case M_DOORS:   GameSprintf(text, "Room transitions: %s", on_off(set_no_doors)); break;
        case M_MARKS:   GameSprintf(text, "AP pickup markers: %s", on_off(set_no_marks)); break;
        case M_GREEN:   GameSprintf(text, "Cleared rooms green: %s", on_off(set_no_green)); break;
        default:        GameSprintf(text, "Close"); break;
        }
        DrawText(text, &text_style, MENU_X + 4, y0 + 4 + i * MENU_LINE_H, LAYER,
                 i == menu_sel ? RGBA(0x80, 0x80, 0x30, 0x80) : RGBA(0x70, 0x70, 0x70, 0x80));
    }
    DrawText("Up/Down select  Left/Right change  L3 close", &text_style, MENU_X,
             y0 + 8 + M_COUNT * MENU_LINE_H, LAYER, RGBA(0x60, 0x60, 0x60, 0x80));
}

static void controls_tick(void)
{
    u16 held = *(volatile u16 *)(PAD0_STRUCT + 2);
    u16 pressed = *(volatile u16 *)(PAD0_STRUCT + 4);

    settings_init();
    if (held & BTN_L3) {
        l3_frames++;
        if (l3_frames == HOLD_FRAMES && !menu_open && !l3_used && !game_busy()) {
            menu_set_open(1);
            l3_used = 1;
        }
    } else {
        /* a tap: shows/hides the minimap, or closes the menu */
        if (l3_frames > 0 && l3_frames < HOLD_FRAMES && !l3_used) {
            if (menu_open)
                menu_set_open(0);
            else if (!game_busy())
                set_hidden = !set_hidden;
        }
        l3_frames = 0;
        l3_used = 0;
    }
    if (!menu_open)
        return;

    if (pressed & BTN_UP)
        step(&menu_sel, M_COUNT, -1);
    else if (pressed & BTN_DOWN)
        step(&menu_sel, M_COUNT, 1);
    else if (pressed & BTN_LEFT)
        menu_change(-1);
    else if (pressed & BTN_RIGHT)
        menu_change(1);
    else if (pressed & BTN_CROSS) {
        if (menu_sel == M_CLOSE)
            menu_set_open(0);
        else
            menu_change(1);
    } else if (pressed & (BTN_CIRCLE | BTN_TRIANGLE))
        menu_set_open(0);
    if (menu_open) {
        minimap_draw(1);      /* live preview: the gameplay hook is skipped while frozen */
        menu_draw();
    }
}

/* ---- hooks ---- */

/* replaces "jal Player_UpdateStep" @ 0x439EC8 */
void minimap_hook(void)
{
    Player_UpdateStep();
    minimap_draw(0);
}

/* replaces "jal Obj_UpdateAll" @ 0x439F00 (runs on frozen frames too) */
void minimap_input_hook(void)
{
    Obj_UpdateAll();
    controls_tick();
}
