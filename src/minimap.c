/* Minimap: the visited rooms of Leon's floor around him, in a corner of the
 * screen.
 * - Room shapes come from the pause map's own model (game.h "area map"): each
 * room is drawn from its floor triangles (kind 1 parts) with its wall band
 * (kind 0 parts, gaps at the doorways) on top, decoded from the model every
 * frame for the visited rooms on the panel. For every piece, the vertices of
 * its parts, taken in the room's frame, also give an oriented box (used for
 * culling, the pickup marker, and as the room's shape when "Room shapes" is off
 * or the room has no triangles). Boxes and the part -> mesh table are built
 * when the map file changes.
 * - Visited = bit 0 of the room's state word (the pause map's own flag). Save
 * rooms (piece flag 0x2, drawn red on the pause map) are red; rooms whose AP
 * pickup locations are all collected are green; rooms with some left get an
 * orange marker (ap_locations.h, as "Pickups left").
 * - Room transitions: each room's door records, remembered in map space while
 * Leon is in it.
 * - Leon's arrow uses the pause map marker's formula and turn (0x6C3EB8).
 * - Drawing: untextured type 4 sprites (game.h "2D primitives"); shapes are
 * filled from ROW_H-pixel rows, since the 4-vertex primitives don't work as a
 * plain object. Identical consecutive rows are merged into one sprite, so
 * straight edges cost one sprite per run.
 * - Controls: tap L3 to show/hide; hold L3 to open the settings menu (the world
 * is frozen while it is open, as for a message box). Settings last until the
 * console resets. Hooks: jal Player_UpdateStep @ 0x439EC8 (GameplayFrame case
 * 0, skipped while the world is frozen) draws the minimap; jal Obj_UpdateAll @
 * 0x439F00 (also runs on frozen frames) reads L3 and runs the menu. */
#include "ap_locations.h"
#include "game.h"

#define LAYER 1    /* the HUD text's layer */
#define GS_Z 65000 /* as the screen fade */
#define MAX_SPRITES                                                            \
  220 /* per frame, so the minimap can't drain the game's prim pool */
#define ROW_H 2.0f /* row height for filled shapes */
#define MAX_TRIS                                                               \
  256 /* triangles per room and kind (the Lab's largest room has 192) */
#define MAX_SPANS 8 /* separate spans per row of one shape */
#define SPAN_EPS                                                               \
  0.5f /* rows whose span ends differ less than this merge into one sprite */
#define ARROW_TIP 5.0f  /* Leon's arrow: centre to tip, */
#define ARROW_BACK 3.0f /* centre to the back edge, */
#define ARROW_W 3.5f    /* half the back edge */
#define ARROW_ROWS 12   /* sprites it can take (1-pixel rows) */
#define LEON_FWD_Z                                                             \
  1.0f /* Leon faces world (sin yaw, cos yaw) (checked in game) */
#define MARK_R 1.5f
#define DOOR_R 1.5f
#define SCREEN_W2                                                              \
  256.0f /* half screen; coordinates are screen-centre relative, y down */
#define SCREEN_H2 224.0f
#define MARGIN 8.0f
#define HOLD_FRAMES 180 /* L3 held this long opens the menu */

/* base colours, alpha scaled by the opacity setting: [0] elsewhere, [1] Leon is
 * in the room */
static const int panel_rgba[4] = {0x00, 0x00, 0x00, 0x40};
static const int room_rgba[2][4] = {{0x30, 0x48, 0x70, 0x60},
                                    {0x50, 0x78, 0x80, 0x70}};
static const int save_rgba[2][4] = {{0x70, 0x18, 0x18, 0x60},
                                    {0x80, 0x48, 0x48, 0x70}};
static const int clear_rgba[2][4] = {{0x20, 0x60, 0x28, 0x60},
                                     {0x48, 0x80, 0x50, 0x70}};
static const int wall_rgba[2][4] = {{0x60, 0x70, 0x80, 0x70},
                                    {0x80, 0x80, 0x80, 0x80}};
static const int dot_rgba[4] = {0x80, 0x10, 0x10, 0x80}; /* Leon: red */
static const int mark_rgba[4] = {0x80, 0x50, 0x10, 0x80};
static const int door_rgba[4] = {0x80, 0x78, 0x10, 0x80}; /* yellow */
static const int door_edge_rgba[4] = {0x00, 0x00, 0x00, 0x80}; /* its border */

static const TextStyle text_style = {8, 0x80808080, 0, 0x100, 0x100, 0};

/* ---- settings (.bss only: the pnach rewrites initialised data every frame)
 * ---- */

static const float zoom_scales[] = {0.03f, 0.045f, 0.06f, 0.09f, 0.13f};
static const float panel_w[] = {80.0f, 112.0f, 150.0f};
static const float panel_h[] = {66.0f, 92.0f, 124.0f};
static const char *const size_names[] = {"Small", "Medium", "Large"};
static const char *const corner_names[] = {"Top right", "Top left",
                                           "Bottom right", "Bottom left"};
static const int opacity_pct[] = {40, 60, 80, 100, 125};
#define N_ZOOM 5
#define N_SIZE 3
#define N_CORNER 4
#define N_OPACITY 5

static int settings_ready;
static int set_hidden; /* 1 = minimap hidden (tap L3) */
static int set_zoom, set_size, set_corner, set_opacity;
static int set_no_doors, set_no_marks, set_no_green,
    set_no_shapes; /* 1 = that feature off */

static void settings_init(void) {
  if (settings_ready)
    return;
  set_zoom = 2;
  set_size = 1;
  set_corner = 0;
  set_opacity = 3;
  settings_ready = 1;
}

/* panel and clip rectangle for this frame */
static float panel_x0, panel_y0, panel_x1, panel_y1, panel_cx, panel_cy,
    map_scale;
static float clip_x0, clip_y0, clip_x1, clip_y1;

static void layout(void) {
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

static void clip_panel(void) {
  clip_x0 = panel_x0;
  clip_y0 = panel_y0;
  clip_x1 = panel_x1;
  clip_y1 = panel_y1;
}

/* ---- math (no libm) ---- */

#define PI 3.14159265f

static float sin_approx(float x) {
  float x2;
  while (x > PI)
    x -= 2.0f * PI;
  while (x < -PI)
    x += 2.0f * PI;
  x2 = x * x;
  return x *
         (1.0f -
          x2 / 6.0f *
              (1.0f - x2 / 20.0f * (1.0f - x2 / 42.0f * (1.0f - x2 / 72.0f))));
}

static float cos_approx(float x) { return sin_approx(x + PI * 0.5f); }

/* ---- primitives ---- */

static u8 *frame_regs; /* this pass's shared GS register list */
static int sprites_left;
static int sprite_floor; /* draw_rect stops at this many left (kept for doors
                            and dot) */
#define SPRITE_RESERVE 60 /* 2 per door (border + fill), plus the arrow */

static int gs_xy(float v) { return (int)((v + 2048.0f) * 16.0f); }

/* TEST and ALPHA as the screen fade: no Z writes, Z always, (Cs - Cd) * As + Cd
 */
static int begin_frame(void) {
  frame_regs = Prim_Alloc(0x60);
  if (!frame_regs)
    return 0;
  GsRegs_Init(frame_regs);
  GsRegs_Set(frame_regs, GS_REG_TEST_1, 0x31001);
  GsRegs_Set(frame_regs, GS_REG_ALPHA_1, 0x44);
  sprites_left = MAX_SPRITES;
  return 1;
}

/* untextured rectangle, clipped; alpha scaled by the opacity setting unless
 * `solid` */
static void draw_rect_a(float x0, float y0, float x1, float y1, const int *rgba,
                        int solid) {
  u8 *obj;
  int *v, col[4];

  if (x0 < clip_x0)
    x0 = clip_x0;
  if (y0 < clip_y0)
    y0 = clip_y0;
  if (x1 > clip_x1)
    x1 = clip_x1;
  if (y1 > clip_y1)
    y1 = clip_y1;
  if (x1 <= x0 || y1 <= y0 || sprites_left <= sprite_floor)
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
  Prim_SetFlags(obj, 1, 0, 1, 0);      /* alpha blending on */
  Prim_SetVertexCount(obj, 2);         /* 2-vertex sprite */
  obj[PRIM_TME_BYTE] &= ~PRIM_TME_BIT; /* untextured */
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

static void draw_rect(float x0, float y0, float x1, float y1, const int *rgba) {
  draw_rect_a(x0, y0, x1, y1, rgba, 0);
}

/* filled convex quad, corners in order around the edge, from ROW_H-pixel rows
 */
static void draw_quad(const float *xy, const int *rgba) {
  float ymin = xy[1], ymax = xy[1], y;
  int i;

  for (i = 1; i < 4; i++) {
    if (xy[i * 2 + 1] < ymin)
      ymin = xy[i * 2 + 1];
    if (xy[i * 2 + 1] > ymax)
      ymax = xy[i * 2 + 1];
  }
  if (ymin < clip_y0)
    ymin = clip_y0;
  if (ymax > clip_y1)
    ymax = clip_y1;
  for (y = ymin; y < ymax; y += ROW_H) {
    float yc = y + ROW_H * 0.5f, x0 = 1e9f, x1 = -1e9f;

    for (i = 0; i < 4; i++) {
      float ax = xy[i * 2], ay = xy[i * 2 + 1];
      float bx = xy[((i + 1) & 3) * 2], by = xy[((i + 1) & 3) * 2 + 1];

      if ((ay <= yc && by > yc) || (by <= yc && ay > yc)) {
        float x = ax + (yc - ay) * (bx - ax) / (by - ay);
        if (x < x0)
          x0 = x;
        if (x > x1)
          x1 = x;
      }
    }
    if (x1 > x0)
      draw_rect(x0, y, x1, y + ROW_H, rgba);
  }
}

/* x range of triangle t (x, y pairs) between y0 and y1; 0 when they don't
 * overlap */
static int tri_band(const float *t, float y0, float y1, float *lo, float *hi) {
  float a = 1e9f, b = -1e9f;
  int i;

  for (i = 0; i < 3; i++) {
    float ax = t[i * 2], ay = t[i * 2 + 1];
    float bx = t[((i + 1) % 3) * 2], by = t[((i + 1) % 3) * 2 + 1];

    if (ay >= y0 && ay <= y1) {
      if (ax < a)
        a = ax;
      if (ax > b)
        b = ax;
    }
    /* where the edge crosses the band's top and bottom */
    if ((ay < y0) != (by < y0) && ay != by) {
      float x = ax + (y0 - ay) * (bx - ax) / (by - ay);
      if (x < a)
        a = x;
      if (x > b)
        b = x;
    }
    if ((ay < y1) != (by < y1) && ay != by) {
      float x = ax + (y1 - ay) * (bx - ax) / (by - ay);
      if (x < a)
        a = x;
      if (x > b)
        b = x;
    }
  }
  if (b < a)
    return 0;
  *lo = a;
  *hi = b;
  return 1;
}

/* fills the union of n triangles (screen x, y pairs) from ROW_H-pixel rows. A
 * triangle counts in every row it touches, so walls thinner than a row still
 * show. Each row's covered ranges merge into spans; a run of rows with the same
 * spans is drawn as one sprite per span. */
static void fill_tris(const float *t, int n, const int *rgba) {
  float ymin = 1e9f, ymax = -1e9f, y;
  float sp0[MAX_SPANS], sp1[MAX_SPANS], run0[MAX_SPANS], run1[MAX_SPANS],
      run_y = 0.0f;
  int i, j, k, ns, nrun = 0;

  for (i = 0; i < n * 3; i++) {
    if (t[i * 2 + 1] < ymin)
      ymin = t[i * 2 + 1];
    if (t[i * 2 + 1] > ymax)
      ymax = t[i * 2 + 1];
  }
  if (ymin < clip_y0)
    ymin = clip_y0;
  if (ymax > clip_y1)
    ymax = clip_y1;
  for (y = ymin; y < ymax + ROW_H; y += ROW_H) {
    ns = 0;
    if (y < ymax) {
      for (i = 0; i < n; i++) {
        float lo, hi;

        if (!tri_band(t + i * 6, y, y + ROW_H, &lo, &hi))
          continue;
        /* insert sorted by start, merging with spans it touches */
        for (j = 0; j < ns && sp0[j] < lo; j++)
          ;
        if (j > 0 && lo <= sp1[j - 1] + SPAN_EPS) {
          j--;
          if (hi > sp1[j])
            sp1[j] = hi;
        } else if (ns < MAX_SPANS) {
          for (k = ns; k > j; k--) {
            sp0[k] = sp0[k - 1];
            sp1[k] = sp1[k - 1];
          }
          sp0[j] = lo;
          sp1[j] = hi;
          ns++;
        } else {
          j = ns - 1; /* out of spans: widen the last one */
          if (lo < sp0[j])
            sp0[j] = lo;
          if (hi > sp1[j])
            sp1[j] = hi;
        }
        /* the grown span may now reach the ones after it */
        while (j + 1 < ns && sp0[j + 1] <= sp1[j] + SPAN_EPS) {
          if (sp1[j + 1] > sp1[j])
            sp1[j] = sp1[j + 1];
          for (k = j + 1; k + 1 < ns; k++) {
            sp0[k] = sp0[k + 1];
            sp1[k] = sp1[k + 1];
          }
          ns--;
        }
      }
    }
    /* same spans as the open run: extend it */
    if (ns == nrun && ns) {
      for (k = 0; k < ns; k++)
        if (sp0[k] - run0[k] > SPAN_EPS || run0[k] - sp0[k] > SPAN_EPS ||
            sp1[k] - run1[k] > SPAN_EPS || run1[k] - sp1[k] > SPAN_EPS)
          break;
      if (k == ns)
        continue;
    }
    for (k = 0; k < nrun; k++)
      draw_rect(run0[k], run_y, run1[k], y, rgba);
    for (k = 0; k < ns; k++) {
      run0[k] = sp0[k];
      run1[k] = sp1[k];
    }
    nrun = ns;
    run_y = y;
  }
}

/* ---- area cache: one oriented box per map piece ---- */
#define MAX_PIECES 192
#define NO_PIECE 0xFF

typedef struct {
  u8 *piece;
  float c, s;           /* cos/sin of the piece's yaw */
  float x0, x1, z0, z1; /* box in the room's frame */
  int ok;
} RoomBox;

static RoomBox boxes[MAX_PIECES];
static int box_count;
static u8 *cached_file;
static u8 part_owner[256];
static u8 *part_mesh[256];  /* first mesh of each part; a part's meshes are
                               consecutive */
static u8 part_mesh_n[256]; /* its mesh count */
static int cached_local;    /* model_parts_local() of the cached model */

static u8 *map_model(u8 *file) {
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

/* nonzero when the model's part matrices place the parts (Anti-Soul Mystery
 * Lab): its meshes are then in each room's own frame, and the matrix of a
 * room's part equals its piece's pos and yaw. Elsewhere the matrices carry no
 * translation and the meshes are already in area map space. */
static int model_parts_local(const u8 *model) {
  int count = *(const int *)(model + MODEL_NODE_COUNT), i;
  const float *m =
      (const float *)(model + *(const int *)(model + MODEL_NODE_OFS));

  if (count <= 0 || count > 1024)
    return 0;
  for (i = 0; i < count; i++, m += 16)
    if (m[12] > 0.5f || m[12] < -0.5f || m[14] > 0.5f || m[14] < -0.5f)
      return 1;
  return 0;
}

/* (mx, mz): a mesh vertex, in area map space, or with `local` already in the
 * room's frame */
static void add_vertex(RoomBox *b, float mx, float mz, int local) {
  const float *pos = (const float *)(b->piece + PIECE_POS);
  float dx = mx - pos[0], dz = mz - pos[2];
  float lx = b->c * dx - b->s * dz, lz = b->s * dx + b->c * dz; /* RotY(-yaw) */

  if (local) {
    lx = mx;
    lz = mz;
  }
  if (!b->ok) {
    b->x0 = b->x1 = lx;
    b->z0 = b->z1 = lz;
    b->ok = 1;
    return;
  }
  if (lx < b->x0)
    b->x0 = lx;
  if (lx > b->x1)
    b->x1 = lx;
  if (lz < b->z0)
    b->z0 = lz;
  if (lz > b->z1)
    b->z1 = lz;
}

static void build_cache(u8 *file) {
  u8 *model, *mesh;
  int i, k, n, local, prev_part = -1;

  cached_file = file;
  box_count = 0;
  cached_local = 0;
  for (i = 0; i < 256; i++) {
    part_owner[i] = NO_PIECE;
    part_mesh[i] = 0;
    part_mesh_n[i] = 0;
  }
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
  local = model_parts_local(model);
  cached_local = local;
  n = *(int *)(model + MODEL_MESH_COUNT);
  mesh = model + *(int *)(model + MODEL_MESH_OFS);
  for (i = 0; i < n; i++) {
    u32 size = *(u32 *)mesh, q;
    int owner, part;

    if (size < 0x50 || size > 0x10000)
      break;
    part = mesh[MESH_PART];
    /* a part's meshes are consecutive (checked on the Lab's map); a later run
     * is ignored */
    if (!part_mesh[part]) {
      part_mesh[part] = mesh;
      part_mesh_n[part] = 1;
    } else if (part == prev_part && part_mesh_n[part] < 255) {
      part_mesh_n[part]++;
    }
    prev_part = part;
    owner = part_owner[part];
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
          add_vertex(&boxes[owner], (float)v[0] / 16.0f, -(float)v[2] / 16.0f,
                     local);
        q += 12 * num;
      }
    }
    mesh += size;
  }
  GamePrintf("[minimap] map file %d: %d pieces cached%s\n",
             *(volatile int *)0x00B90970, box_count,
             local ? " (room-local meshes)" : "");
}

/* ---- rooms ---- */

static int room_visited(const u8 *piece) {
  int key = GetRoomKey(piece[0], piece[PIECE_ROOM]);
  u32 *table = ROOM_STATE;

  if (!table || key < 0 || key >= ROOM_STATE_COUNT)
    return 0;
  return table[key * 3] & 1;
}

/* AP pickup locations in this room: how many, and how many still have their
 * collected flag clear */
static void room_pickups(const u8 *piece, int *total, int *left) {
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

static void local_to_map(const RoomBox *b, float lx, float lz, float *mx,
                         float *mz) {
  const float *pos = (const float *)(b->piece + PIECE_POS);

  *mx = pos[0] + b->c * lx + b->s * lz;
  *mz = pos[2] - b->s * lx + b->c * lz;
}

/* world -> map in the room `piece` belongs to, as the pause map marker
 * (0x6C3EB8) */
static void world_to_map(const u8 *piece, float wx, float wz, float *mx,
                         float *mz) {
  const float *pos = (const float *)(piece + PIECE_POS);
  const float *scale = (const float *)(piece + PIECE_SCALE);
  float c = cos_approx(pos[3]), s = sin_approx(pos[3]);
  float x = wx * 0.1f, z = wz * 0.1f;

  *mx = pos[0] + scale[0] * (c * x + s * z);
  *mz = pos[2] + scale[2] * (-s * x + c * z);
}

/* ---- room transitions ----
 * Door records exist only for the loaded room (ROOMDATA object list 0, game.h
 * "rooms"), so each room's doors are remembered in map space when Leon is in
 * it, until the console resets. */
#define MAX_ROOMS 416
#define MAX_DOORS 8

typedef struct {
  short x, z; /* map units */
  signed char floor;
  u8 pad;
} DoorMark;

static DoorMark doors[MAX_ROOMS][MAX_DOORS];
static u8
    door_count[MAX_ROOMS]; /* doors + 1 once the room was read, 0 = not yet */

static void read_doors(const u8 *here, int key) {
  u8 *rd = ROOMDATA, *list;
  int count, i, n = 0;

  if (!rd || key < 0 || key >= MAX_ROOMS || door_count[key])
    return;
  list = *(u8 **)(*(u8 **)(rd + ROOMDATA_OBJLISTS) + 4); /* object list 0 */
  if (!list)
    return;
  count = *(int *)(list + OBJLIST_COUNT);
  for (i = 0; i < count && n < MAX_DOORS; i++) {
    const u8 *rec = list + 0x10 + 0x80 * i;
    const float *wpos = (const float *)rec;
    float mx, mz;

    if (*(const short *)(rec + DOOR_DEST_STAGE) < 0 ||
        *(const short *)(rec + DOOR_DEST_ROOM) < 0)
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

static int game_busy(void) {
  u8 *box = MsgBox_Get();
  return IsWorldFrozen() || (*(volatile u8 *)0x00B36750 & 1) ||
         (box && *(volatile int *)(box + MSGBOX_OPEN_FLAG));
}

/* map z grows towards the top of the pause map (north), screen y grows
 * downwards */
static void map_to_screen(float mx, float mz, float cx, float cz, float *sx,
                          float *sy) {
  *sx = panel_cx + (mx - cx) * map_scale;
  *sy = panel_cy - (mz - cz) * map_scale;
}

/* ---- room triangles, decoded from the part's meshes (game.h "area map") ----
 */

static float tri_buf[MAX_TRIS * 6]; /* screen x, y of 3 corners per triangle */

#define MAX_POS_BLOCKS                                                         \
  4 /* position unpacks per batch (one in the Lab's meshes) */

/* appends the triangles of one index list (a batch's triangle strip) to
 * tri_buf; returns n */
static int strip_tris(const RoomBox *b, const u16 *idx, int count,
                      const u8 *const *pos, const int *pos_addr,
                      const int *pos_num, int blocks, float cx, float cz,
                      int n) {
  float wx[2], wy[2];
  int k, have = 0;

  for (k = 0; k < count && n < MAX_TRIS; k++) {
    int a = idx[k] & 0x7FFF, j, off = 0;
    const int *v = 0;
    float mx, mz, sx, sy;

    for (j = 0; j < blocks; j++) {
      off = a - pos_addr[j];
      if (off >= 0 && !(off & 3) && off / 4 < pos_num[j]) {
        v = (const int *)(pos[j] + 12 * (off / 4));
        break;
      }
    }
    if (!v) { /* not a vertex of this batch: restart the strip */
      have = 0;
      continue;
    }
    mx = (float)v[0] / 16.0f;
    mz = -(float)v[2] / 16.0f;
    if (cached_local)
      local_to_map(b, mx, mz, &mx, &mz);
    map_to_screen(mx, mz, cx, cz, &sx, &sy);
    if (have >= 2 && !(idx[k] & 0x8000)) {
      float *t = tri_buf + n * 6;
      t[0] = wx[0];
      t[1] = wy[0];
      t[2] = wx[1];
      t[3] = wy[1];
      t[4] = sx;
      t[5] = sy;
      n++;
    }
    wx[0] = wx[1];
    wy[0] = wy[1];
    wx[1] = sx;
    wy[1] = sy;
    have++;
  }
  return n;
}

/* appends the triangles of every mesh of `part` to tri_buf, in screen space;
 * returns n */
static int part_tris(const RoomBox *b, int part, float cx, float cz, int n) {
  u8 *mesh = part_mesh[part];
  int m;

  for (m = 0; mesh && m < part_mesh_n[part]; m++) {
    u32 size = *(u32 *)mesh, q = 0x50;
    const u8 *pos[MAX_POS_BLOCKS];
    int pos_addr[MAX_POS_BLOCKS], pos_num[MAX_POS_BLOCKS], blocks = 0;

    if (size < 0x50 || size > 0x10000)
      break;
    while (q + 4 <= size) {
      u32 w = *(u32 *)(mesh + q);
      int cmd = (w >> 24) & 0x7F, num = (w >> 16) & 0xFF, imm = w & 0xFFFF;

      q += 4;
      if ((cmd & 0x60) == 0x60) { /* UNPACK: vn = components - 1, vl = width */
        int vn = (cmd >> 2) & 3, vl = cmd & 3, addr = imm & 0x3FF;
        u32 bytes;

        if (!num)
          num = 256;
        bytes = vl == 3 ? 2 * num : (vn + 1) * (4 >> vl) * num;
        bytes = (bytes + 3) & ~3u;
        if (q + bytes > size)
          break;
        if (cmd == VIF_UNPACK_V3_32 && blocks < MAX_POS_BLOCKS) {
          pos[blocks] = mesh + q;
          pos_addr[blocks] = addr;
          pos_num[blocks] = num;
          blocks++;
        } else if (cmd == VIF_UNPACK_V4_16 && addr > 0x10 && blocks) {
          n = strip_tris(b, (const u16 *)(mesh + q), 4 * num, pos, pos_addr,
                         pos_num, blocks, cx, cz, n);
          blocks = 0; /* the next batch uploads its own vertices */
        }
        q += bytes;
      } else if (cmd == 0x50 ||
                 cmd == 0x51) { /* DIRECT / DIRECTHL: imm quadwords */
        q += 16 * imm;
      } else if (cmd == 0x30 || cmd == 0x31) { /* STROW / STCOL */
        q += 16;
      } else if (cmd == 0x20) { /* STMASK */
        q += 4;
      }
    }
    mesh += size;
  }
  return n;
}

static int piece_tris(const RoomBox *b, int kind, float cx, float cz);

/* one visited room on Leon's floor: its floor and walls (or its box), and the
 * pickup marker */
static void draw_room(const RoomBox *b, int is_here, int floor, float cx,
                      float cz) {
  const float lx[4] = {b->x0, b->x1, b->x1, b->x0};
  const float lz[4] = {b->z0, b->z0, b->z1, b->z1};
  const int (*rgba)[4];
  float q[8], mx, mz, sx, sy, x0 = 1e9f, x1 = -1e9f, y0 = 1e9f, y1 = -1e9f;
  int j, n, total, left;

  if (!b->ok || (signed char)b->piece[PIECE_FLOOR] != floor)
    return;
  if (!is_here && !room_visited(b->piece))
    return;
  for (j = 0; j < 4; j++) {
    local_to_map(b, lx[j], lz[j], &mx, &mz);
    map_to_screen(mx, mz, cx, cz, &q[j * 2], &q[j * 2 + 1]);
    if (q[j * 2] < x0)
      x0 = q[j * 2];
    if (q[j * 2] > x1)
      x1 = q[j * 2];
    if (q[j * 2 + 1] < y0)
      y0 = q[j * 2 + 1];
    if (q[j * 2 + 1] > y1)
      y1 = q[j * 2 + 1];
  }
  if (x1 < clip_x0 || x0 > clip_x1 || y1 < clip_y0 || y0 > clip_y1)
    return; /* off the panel: don't decode it */
  /* save rooms red (they have no pickups); rooms whose AP pickups are all taken
   * green */
  room_pickups(b->piece, &total, &left);
  if (*(const u16 *)(b->piece + PIECE_FLAGS) & PIECE_FLAG_SAVE)
    rgba = save_rgba;
  else if (total && !left && !set_no_green)
    rgba = clear_rgba;
  else
    rgba = room_rgba;
  n = set_no_shapes ? 0 : piece_tris(b, 1, cx, cz);
  if (n) {
    fill_tris(tri_buf, n, rgba[is_here]);
    n = piece_tris(b, 0, cx, cz);
    if (n)
      fill_tris(tri_buf, n, wall_rgba[is_here]);
  } else {
    draw_quad(q,
              rgba[is_here]); /* no floor triangles, or shapes off: the box */
  }
  if (left && !set_no_marks) {
    local_to_map(b, (b->x0 + b->x1) * 0.5f, (b->z0 + b->z1) * 0.5f, &mx, &mz);
    map_to_screen(mx, mz, cx, cz, &sx, &sy);
    draw_rect(sx - MARK_R, sy - MARK_R, sx + MARK_R, sy + MARK_R, mark_rgba);
  }
}

/* the triangles of the piece's parts of one kind (0 = wall band, 1 = floor),
 * into tri_buf */
static int piece_tris(const RoomBox *b, int kind, float cx, float cz) {
  const u16 *counts = (const u16 *)(b->piece + PIECE_COUNTS);
  const u8 *parts = b->piece + (kind ? PIECE_OUTLINE : PIECE_FILL);
  int k, n = 0;

  for (k = 0; k < counts[kind] && k < 4; k++)
    n = part_tris(b, parts[k], cx, cz, n);
  return n;
}

/* Leon's arrow at the panel centre, pointing his way on the map: his facing
 * through the room's world -> map turn, as the pause map arrow (yaw + room
 * yaw). Filled from 1-pixel rows; a plain dot when the model is missing. */
static void draw_leon(const u8 *here) {
  const u8 *model = PLAYER_MODEL;
  const float *scale = (const float *)(here + PIECE_SCALE);
  float yaw, c, s, fx, fz, dx, dy, len, t[6], y, ymin, ymax;
  int i;

  if (!model) {
    draw_rect(panel_cx - 2.0f, panel_cy - 2.0f, panel_cx + 2.0f,
              panel_cy + 2.0f, dot_rgba);
    return;
  }
  yaw = ((const float *)(model + MODEL_ROT))[1];
  c = cos_approx(((const float *)(here + PIECE_POS))[3]);
  s = sin_approx(((const float *)(here + PIECE_POS))[3]);
  fx = sin_approx(yaw);
  fz = LEON_FWD_Z * cos_approx(yaw);
  /* world direction -> map (world_to_map's linear part) -> screen (y down) */
  dx = scale[0] * (c * fx + s * fz);
  dy = -scale[2] * (-s * fx + c * fz);
  len = dx * dx + dy * dy;
  if (len < 1e-6f)
    return;
  /* 1/sqrt(len) by Newton steps from 1 (len is near 1 unless the room is
   * scaled) */
  {
    float r = 1.0f;
    for (i = 0; i < 4; i++)
      r = r * (1.5f - 0.5f * len * r * r);
    dx *= r;
    dy *= r;
  }
  t[0] = panel_cx + dx * ARROW_TIP;
  t[1] = panel_cy + dy * ARROW_TIP;
  t[2] = panel_cx - dx * ARROW_BACK - dy * ARROW_W;
  t[3] = panel_cy - dy * ARROW_BACK + dx * ARROW_W;
  t[4] = panel_cx - dx * ARROW_BACK + dy * ARROW_W;
  t[5] = panel_cy - dy * ARROW_BACK - dx * ARROW_W;
  ymin = ymax = t[1];
  for (i = 1; i < 3; i++) {
    if (t[i * 2 + 1] < ymin)
      ymin = t[i * 2 + 1];
    if (t[i * 2 + 1] > ymax)
      ymax = t[i * 2 + 1];
  }
  for (y = ymin; y < ymax; y += 1.0f) {
    float lo, hi;

    if (tri_band(t, y, y + 1.0f, &lo, &hi))
      draw_rect(lo, y, hi < lo + 1.0f ? lo + 1.0f : hi, y + 1.0f, dot_rgba);
  }
}

/* draws the minimap; `preview` = called from the menu (world frozen by us) */
static void minimap_draw(int preview) {
  u8 *file = MAP_FILE, *here;
  float cx, cz, sx, sy;
  int floor, i;

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

  /* rooms leave SPRITE_RESERVE sprites for the doors and Leon's arrow; Leon's
   * room goes first */
  sprite_floor = SPRITE_RESERVE;
  for (i = 0; i < box_count; i++)
    if (boxes[i].piece == here)
      draw_room(&boxes[i], 1, floor, cx, cz);
  for (i = 0; i < box_count; i++)
    if (boxes[i].piece != here)
      draw_room(&boxes[i], 0, floor, cx, cz);
  sprite_floor = ARROW_ROWS; /* the doors leave the arrow's */

  /* room transitions, on top of the rooms (overlaps between neighbours are fine
   * for now) */
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
      /* a dark border keeps the mark visible on the pale walls */
      draw_rect(sx - DOOR_R - 1.0f, sy - DOOR_R - 1.0f, sx + DOOR_R + 1.0f,
                sy + DOOR_R + 1.0f, door_edge_rgba);
      draw_rect(sx - DOOR_R, sy - DOOR_R, sx + DOOR_R, sy + DOOR_R, door_rgba);
    }
  }
  sprite_floor = 0;
  draw_leon(here);
}

/* ---- L3 and the settings menu ---- */

enum {
  M_SHOW,
  M_ZOOM,
  M_SIZE,
  M_CORNER,
  M_OPACITY,
  M_SHAPES,
  M_DOORS,
  M_MARKS,
  M_GREEN,
  M_CLOSE,
  M_COUNT
};

static int menu_open, menu_sel;
static int l3_frames; /* frames L3 has been held */
static int l3_used;   /* this L3 press already opened/closed the menu */

static void menu_set_open(int open) {
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

static void step(int *value, int count, int dir) {
  *value = (*value + dir + count) % count;
}

static void menu_change(int dir) {
  switch (menu_sel) {
  case M_SHOW:
    set_hidden = !set_hidden;
    break;
  case M_ZOOM:
    step(&set_zoom, N_ZOOM, dir);
    break;
  case M_SIZE:
    step(&set_size, N_SIZE, dir);
    break;
  case M_CORNER:
    step(&set_corner, N_CORNER, dir);
    break;
  case M_OPACITY:
    step(&set_opacity, N_OPACITY, dir);
    break;
  case M_SHAPES:
    set_no_shapes = !set_no_shapes;
    break;
  case M_DOORS:
    set_no_doors = !set_no_doors;
    break;
  case M_MARKS:
    set_no_marks = !set_no_marks;
    break;
  case M_GREEN:
    set_no_green = !set_no_green;
    break;
  }
}

static const char *on_off(int off) { return off ? "Off" : "On"; }

#define MENU_LINE_H 20 /* the font is about 18 px tall at scale 0x100 */

#define MENU_X (-236) /* left edge of the screen, 20 px in */

static void menu_draw(void) {
  char text[48];
  int i, y0 = -110;

  DrawText("Minimap", &text_style, MENU_X, y0 - 20, LAYER,
           RGBA(0x80, 0x80, 0x80, 0x80));
  for (i = 0; i < M_COUNT; i++) {
    switch (i) {
    case M_SHOW:
      GameSprintf(text, "Minimap: %s", on_off(set_hidden));
      break;
    case M_ZOOM:
      GameSprintf(text, "Zoom: %d / %d", set_zoom + 1, N_ZOOM);
      break;
    case M_SIZE:
      GameSprintf(text, "Size: %s", size_names[set_size]);
      break;
    case M_CORNER:
      GameSprintf(text, "Corner: %s", corner_names[set_corner]);
      break;
    case M_OPACITY:
      GameSprintf(text, "Opacity: %d%%", opacity_pct[set_opacity]);
      break;
    case M_SHAPES:
      GameSprintf(text, "Room shapes: %s", on_off(set_no_shapes));
      break;
    case M_DOORS:
      GameSprintf(text, "Room transitions: %s", on_off(set_no_doors));
      break;
    case M_MARKS:
      GameSprintf(text, "AP pickup markers: %s", on_off(set_no_marks));
      break;
    case M_GREEN:
      GameSprintf(text, "Cleared rooms green: %s", on_off(set_no_green));
      break;
    default:
      GameSprintf(text, "Close");
      break;
    }
    DrawText(text, &text_style, MENU_X + 4, y0 + 4 + i * MENU_LINE_H, LAYER,
             i == menu_sel ? RGBA(0x80, 0x80, 0x30, 0x80)
                           : RGBA(0x70, 0x70, 0x70, 0x80));
  }
  DrawText("Up/Down select  Left/Right change  L3 close", &text_style, MENU_X,
           y0 + 8 + M_COUNT * MENU_LINE_H, LAYER, RGBA(0x60, 0x60, 0x60, 0x80));
}

static void controls_tick(void) {
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
    minimap_draw(
        1); /* live preview: the gameplay hook is skipped while frozen */
    menu_draw();
  }
}

/* ---- hooks ---- */

/* replaces "jal Player_UpdateStep" @ 0x439EC8 */
void minimap_hook(void) {
  Player_UpdateStep();
  minimap_draw(0);
}

/* replaces "jal Obj_UpdateAll" @ 0x439F00 (runs on frozen frames too) */
void minimap_input_hook(void) {
  Obj_UpdateAll();
  controls_tick();
}
