/* Shop Sanity: AP locations in Rinaldo's shop (layout and protocol in apshop.h).
 *
 * Shop (RE, SLUS-20733; the buy/sell menu is Shop_Update? 0x6E12B0, list widget at 0xBACB28):
 * - List: Shop_BuildList 0x6E0FE8(sell, buf), called at 0x6E1348 (menu opens) and 0x6E1484
 *   (rebuilt after every purchase), fills 0xBAC678 with {0x806E0E20 draw fn, item ID, greyed}
 *   for each kind in 0x79A478 (0 usable 0x2A-0x54, 1 key 0x55-0x7E, 3 armour, 9 orbs,
 *   4 accessories 0x0A-0x29, 8 relics), every ID whose Shop_ItemState? 0x6E06B0 isn't 3.
 * - State 0x6E06B0(id): 3 when the discounted buy price is 0 or a max-stack-1 item is held,
 *   2 when the stack is full, 1 when gold < price, 0 = can buy.
 * - Price: Shop_Price? 0x6E0630(id, sell): buy = 0x6B79B8(id) * (1 - 0.1 * Member Plates worn);
 *   0x6B79B8 reads the info record (Item_GetInfo): usable s16 +0x44, key/orb/relic int +0x40,
 *   armour/accessory int +0x44 (sell: +0x46 s16 / +0x44 / +0x48).
 * - Buy (state 3, case 7): AddGold(-price * n) then Inv_AddItem(id, n) @ 0x6E1AEC; n is at most
 *   min(max stack - held, gold / price) (0x6E08B8, which divides by the price).
 * - Row: 0x6E0998: icon ^Ixx from the record's +0x20, Item_GetListText (name), held count, price.
 *   Selected row: Item_GetDescTextSafe in the description box, the record's model (+0x24,
 *   palette +0x28) turning beside it.
 *
 * AP rows: item IDs with blank info records that nothing else uses (shop_ids). Each time the
 * list is built (shop_list_hook) the first unchecked table slots get those IDs; their records
 * become copies of a sold item of the same category with the slot's price, a gem's icon and model
 * and text IDs SHOP_TEXT_NAME/DESC + slot, which item_text_hook (ticket.c) answers with the
 * table's text. The list is then reordered so the AP rows come last, in table order.
 * Buying one (shop_buy_hook) gives nothing and checks the slot; the rebuild that follows takes
 * it off the list. Records only change when the list is built (the shop divides by the price of
 * the selected row, so a row's price must not drop to 0 while the menu shows it) and are
 * rewritten every frame from that state (a console reset reloads the game's data).
 *
 * Hooks (config.toml, Minimap patch): jal Shop_BuildList @ 0x6E1348 / 0x6E1484 ->
 * shop_list_hook, jal Inv_AddItem @ 0x6E1AEC -> shop_buy_hook. */
#include "apshop.h"

#define SHOP_TEXT_NAME 0x7D00   /* + slot: row name (clear of the ticket's 0x7E00, keys' 0x7F00) */
#define SHOP_TEXT_DESC 0x7D40   /* + slot: description */

#define W_NAME       0          /* info record words, the same in every category used here */
#define W_NAME_ALT   1
#define W_DESC_SHORT 2
#define W_DESC       3
#define W_DESC_ALT   5
#define W_DESC_SHORT2 6
#define W_DESC2      7
#define W_ICON       8
#define W_MODEL      9
#define W_PALETTE    10
#define W_MAX_STACK  13

/* where a category keeps its buy price (and sell price, cleared for AP rows) */
enum { PRICE_S16_44, PRICE_INT_40, PRICE_INT_44 };

typedef struct {
    u8 template_id;   /* sold item of the category the AP record is copied from */
    u8 words;         /* record size / 4 */
    u8 price;         /* PRICE_* */
} Category;

static const Category cat_usable = {0x3C, 0x50 / 4, PRICE_S16_44};     /* Diamond */
static const Category cat_key    = {0x60, 0x48 / 4, PRICE_INT_40};     /* Music Box */
static const Category cat_acc    = {0x1A, 0x84 / 4, PRICE_INT_44};     /* Sacrificial Doll */

/* AP row item IDs, in Buy list order: blank usable records (0x4D is the Savewarp Ticket), blank
 * key items (0x74-0x78 are the area keys), blank accessories */
static const u8 shop_ids[SHOP_SHOWN_MAX] = {
    0x4E, 0x4F, 0x50, 0x51, 0x52, 0x53, 0x54,
    0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E,
    0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29,
};

static const Category *category_of(int id)
{
    return id >= 0x55 ? &cat_key : id >= 0x2A ? &cat_usable : &cat_acc;
}

/* the vanilla shop items, in SV_* bit order, with their vanilla buy price */
typedef struct {
    u8 id;
    u8 price_at;      /* PRICE_* */
    u16 price;
} Vanilla;

static const Vanilla vanilla_items[] = {
    {0x2A, PRICE_S16_44, 200},   {0x2B, PRICE_S16_44, 800},  {0x2F, PRICE_S16_44, 100},
    {0x30, PRICE_S16_44, 100},   {0x31, PRICE_S16_44, 200},  {0x32, PRICE_S16_44, 800},
    {0x3C, PRICE_S16_44, 10000}, {0x3D, PRICE_S16_44, 3000}, {0x3E, PRICE_S16_44, 2000},
    {0x3F, PRICE_S16_44, 1000},  {0x40, PRICE_S16_44, 800},  {0x41, PRICE_S16_44, 400},
    {0x60, PRICE_INT_40, 3150},  {0x1A, PRICE_INT_44, 2000}, {0x8C, PRICE_INT_40, 3000},
};
#define VANILLA_COUNT ((int)(sizeof(vanilla_items) / sizeof(vanilla_items[0])))

/* SHOP_LOOK_*: a gem's icon and its palette of the gem model 0x31 */
#define GEM_MODEL 0x31
static const u8 look_icon[SHOP_LOOK_COUNT]    = {0x36, 0x35, 0x37};  /* Turquoise, Sapphire, Ruby */
static const u8 look_palette[SHOP_LOOK_COUNT] = {2, 1, 3};

/* state lives in .bss (the pnach rewrites initialised data every frame); set when the list is
 * built */
static int built;                        /* the list has been built since boot */
static u8 row_slot[SHOP_SHOWN_MAX];      /* table slot + 1 of each AP row, 0 = not on sale */
static u16 row_price[SHOP_SHOWN_MAX];
static u8 row_look[SHOP_SHOWN_MAX];
static u32 vanilla_mask;                 /* SV_* bits on sale */

static int table_count(void)
{
    volatile ShopTable *t = SHOP_TABLE;

    if (t->magic != SHOP_TABLE_MAGIC)
        return 0;
    return t->count < SHOP_SLOTS_MAX ? (int)t->count : SHOP_SLOTS_MAX;
}

static int row_of(int id)
{
    int k;

    for (k = 0; k < SHOP_SHOWN_MAX; k++)
        if (shop_ids[k] == id)
            return k;
    return -1;
}

static void set_price(u32 *rec, int at, int price)
{
    switch (at) {
    case PRICE_S16_44:          /* s16 buy, s16 sell */
        rec[0x44 / 4] = (rec[0x44 / 4] & 0xFFFF0000) | (price & 0xFFFF);
        break;
    case PRICE_INT_40:
        rec[0x40 / 4] = price;
        break;
    default:
        rec[0x44 / 4] = price;
        break;
    }
}

/* AP row k's info record: a copy of its category's template with the slot's text and price, or
 * just no buy price (not on sale) */
static void write_row(int k)
{
    int id = shop_ids[k], slot = row_slot[k] - 1, w;
    const Category *c = category_of(id);
    u32 *rec = (u32 *)Item_GetInfo(id);
    const u32 *src = (const u32 *)Item_GetInfo(c->template_id);
    u32 desc;

    if (!rec || !src)
        return;
    if (slot < 0) {
        set_price(rec, c->price, 0);
        return;
    }
    for (w = 0; w < c->words; w++)
        rec[w] = src[w];
    desc = SHOP_TEXT_DESC + slot;
    rec[W_NAME] = rec[W_NAME_ALT] = SHOP_TEXT_NAME + slot;
    rec[W_DESC_SHORT] = rec[W_DESC] = rec[W_DESC_ALT] = desc;
    rec[W_DESC_SHORT2] = rec[W_DESC2] = desc;
    rec[W_ICON] = look_icon[row_look[k]];
    rec[W_MODEL] = GEM_MODEL;
    rec[W_PALETTE] = look_palette[row_look[k]];
    rec[W_MAX_STACK] = 1;
    switch (c->price) {          /* the sell price: 0, so it could never be sold */
    case PRICE_S16_44:
        rec[0x44 / 4] = row_price[k];
        break;
    case PRICE_INT_40:
        rec[0x40 / 4] = row_price[k];
        rec[0x44 / 4] = 0;
        break;
    default:
        rec[0x44 / 4] = row_price[k];
        rec[0x48 / 4] = 0;
        break;
    }
}

static void write_records(void)
{
    int k, i;

    for (k = 0; k < SHOP_SHOWN_MAX; k++)
        write_row(k);
    for (i = 0; i < VANILLA_COUNT; i++) {
        const Vanilla *v = &vanilla_items[i];
        u32 *rec = (u32 *)Item_GetInfo(v->id);

        if (rec)
            set_price(rec, v->price_at, (vanilla_mask >> i) & 1 ? v->price : 0);
    }
}

/* the AP rows and vanilla items for the list about to be built, from the table */
static void assign(void)
{
    volatile ShopTable *t = SHOP_TABLE;
    int n = table_count(), i, k = 0;

    for (i = 0; i < n && k < SHOP_SHOWN_MAX; i++) {
        volatile ShopSlot *s = &t->slot[i];
        u32 price = s->price;

        if (s->checked)
            continue;
        if (price < SHOP_PRICE_MIN)
            price = SHOP_PRICE_MIN;
        if (price > SHOP_PRICE_MAX)
            price = SHOP_PRICE_MAX;
        row_slot[k] = i + 1;
        row_price[k] = price;
        row_look[k] = s->look < SHOP_LOOK_COUNT ? s->look : SHOP_LOOK_FILLER;
        k++;
    }
    for (; k < SHOP_SHOWN_MAX; k++)
        row_slot[k] = 0;
    vanilla_mask = t->magic == SHOP_TABLE_MAGIC ? t->vanilla & SV_ALL : SV_ALL;
    built = 1;
    write_records();
}

/* AP rows to the end of the Buy list (they come in three groups, by category), in slot order */
static void reorder(u32 *buf)
{
    u32 ap[SHOP_SHOWN_MAX][3];
    int n = 0, out = 0, i, w;

    for (i = 0; buf[i * 3] && i < 99; i++) {
        int k = row_of(buf[i * 3 + 1]);

        if (k >= 0 && n < SHOP_SHOWN_MAX) {
            for (w = 0; w < 3; w++)
                ap[n][w] = buf[i * 3 + w];
            n++;
        } else {
            for (w = 0; w < 3; w++)
                buf[out * 3 + w] = buf[i * 3 + w];
            out++;
        }
    }
    for (i = 0; i < n; i++, out++)
        for (w = 0; w < 3; w++)
            buf[out * 3 + w] = ap[i][w];
}

void Shop_BuildList(int sell, u32 *buf);       /* 0x6E0FE8 */

/* Replaces "jal Shop_BuildList" @ 0x6E1348 / 0x6E1484 */
void shop_list_hook(int sell, u32 *buf)
{
    if (!sell)
        assign();
    Shop_BuildList(sell, buf);
    if (!sell)
        reorder(buf);
}

/* Replaces "jal Inv_AddItem" @ 0x6E1AEC, the Buy side of a purchase (gold is already taken) */
int shop_buy_hook(int id, int count)
{
    volatile ShopTable *t = SHOP_TABLE;
    int k = row_of(id), slot;

    if (k < 0)
        return Inv_AddItem(id, count);
    slot = row_slot[k] - 1;
    if (slot >= 0 && slot < table_count() && !t->slot[slot].checked) {
        t->slot[slot].checked = 1;
        t->slot[slot].report = 1;          /* pickup.c posts the EV_LOCATION */
        t->checked_seq = t->checked_seq + 1;
        GamePrintf("[shop] slot %d bought (game_key %X, %d gold)\n", slot,
                   t->slot[slot].game_key, row_price[k]);
    }
    return 0;
}

/* item_text_hook (ticket.c): the text of an AP row */
char *shop_text(int text_id)
{
    volatile ShopTable *t = SHOP_TABLE;
    int slot;

    if (text_id < SHOP_TEXT_NAME || text_id >= SHOP_TEXT_DESC + SHOP_SLOTS_MAX)
        return 0;
    slot = (text_id - SHOP_TEXT_NAME) % SHOP_SLOTS_MAX;
    if (slot >= table_count())
        return text_id < SHOP_TEXT_DESC ? "AP Item" : "";
    if (text_id < SHOP_TEXT_DESC) {
        t->slot[slot].name[SHOP_NAME_BYTES - 1] = '\0';
        return (char *)t->slot[slot].name;
    }
    t->slot[slot].desc[SHOP_DESC_BYTES - 1] = '\0';
    return (char *)t->slot[slot].desc;
}

void apshop_frame(void)
{
    if (built)
        write_records();
}
