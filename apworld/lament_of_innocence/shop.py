"""Shop Sanity: AP locations sold in Rinaldo's shop.

The game side (src/apshop.h) and the client (game_interface.py sync_shop, client.py setup_shop)
read slot_data:
  shop_sanity     0 = off (the vanilla shop)
  shop_vanilla    bit i set = SHOP_VANILLA[i] stays on sale (apshop.h SV_* order)
  shop_locations  AP location ids, slot order; slot i is game_key SHOP_KEY_BASE + i
  shop_prices     gold per slot, same order (the game clamps to SHOP_PRICE_MIN..SHOP_PRICE_MAX)

Rinaldo's stock has 35 rows; every vanilla item taken off sale frees a row for an AP slot, so
there are SHOP_ROWS - (vanilla items kept) slots (20..35). The Buy list shows the first
SHOP_SHOWN_MAX unchecked slots, so later slots appear as earlier ones are bought.
"""
from typing import TYPE_CHECKING, Dict, FrozenSet, List, Tuple

if TYPE_CHECKING:
    from . import LoIWorld

# Location ids: a fresh block. EXTRA_BASE_ID + game_key (< 0x8000) ends below 207372768 and the
# torches (TORCH_BASE_ID + n, n < 1536) below 207351536, so nothing else can land here.
SHOP_BASE_ID = 207380000
SHOP_SLOTS_MAX = 64          # apshop.h SHOP_SLOTS_MAX: every slot always has a name and an id
SHOP_SHOWN_MAX = 20          # apshop.h SHOP_SHOWN_MAX: AP rows on the Buy list at once
SHOP_ROWS = 35               # slots = SHOP_ROWS - vanilla items kept
SHOP_KEY_BASE = 0x20000      # game_key of slot i = SHOP_KEY_BASE + i
SHOP_PRICE_MIN, SHOP_PRICE_MAX = 2, 30000   # what the game charges at least / at most
SHOP_REGION = "PttDA"

# (item name, option name), in the bit order of slot_data["shop_vanilla"] (apshop.h SV_*,
# game_interface.py SHOP_VANILLA_ITEMS)
SHOP_VANILLA: Tuple[Tuple[str, str], ...] = (
    ("Potion", "shop_potion"),
    ("High Potion", "shop_high_potion"),
    ("Serum", "shop_serum"),
    ("Uncurse Potion", "shop_uncurse_potion"),
    ("Magical Ticket", "shop_magical_ticket"),
    ("Memorial Ticket", "shop_memorial_ticket"),
    ("Diamond", "shop_diamond"),
    ("Ruby", "shop_ruby"),
    ("Sapphire", "shop_sapphire"),
    ("Opal", "shop_opal"),
    ("Turquoise", "shop_turquoise"),
    ("Zircon", "shop_zircon"),
    ("Music Box", "shop_music_box"),
    ("Sacrificial Doll", "shop_sacrificial_doll"),
    ("White Bishop", "shop_white_bishop"),
)
SHOP_VANILLA_ALL = (1 << len(SHOP_VANILLA)) - 1

PRICE_STEP = 10   # every rolled price is a multiple of this

# Shop Prices (options.ShopPrices value) -> (low, high) gold, both inclusive
PRICE_RANGES: Dict[int, Tuple[int, int]] = {
    1: (0, 500),        # affordable
    2: (500, 2000),     # normal
    3: (1000, 5000),    # unaffordable
}


def shop_location_name(slot: int) -> str:
    """Slot 0 is "Rinaldo's Shop: Item 1"."""
    return f"Rinaldo's Shop: Item {slot + 1}"


SHOP_LOCATION_NAME_TO_ID: Dict[str, int] = {shop_location_name(i): SHOP_BASE_ID + i
                                            for i in range(SHOP_SLOTS_MAX)}


def vanilla_mask(world: "LoIWorld") -> int:
    """slot_data["shop_vanilla"]: bit i = SHOP_VANILLA[i] stays on sale."""
    return sum(1 << i for i, (_, opt) in enumerate(SHOP_VANILLA) if getattr(world.options, opt).value)


def kept_vanilla_items(world: "LoIWorld") -> FrozenSet[str]:
    """The vanilla items that stay on sale: a shop location never holds one of this world's own
    copies of them (you can buy those anyway)."""
    return frozenset(name for name, opt in SHOP_VANILLA if getattr(world.options, opt).value)


def slot_count(world: "LoIWorld") -> int:
    """AP shop slots in this slot's game (0 with Shop Sanity off)."""
    if not world.options.shop_sanity:
        return 0
    return SHOP_ROWS - bin(vanilla_mask(world)).count("1")


def roll_prices(world: "LoIWorld", count: int) -> List[int]:
    """Gold per slot, random in the mode's range, in steps of PRICE_STEP (2178 -> 2180), so never
    below PRICE_STEP. custom: up to Shop Custom Price; a custom price under PRICE_STEP is used
    as is for every slot."""
    mode = world.options.shop_prices
    if mode == mode.option_custom:
        low, high = SHOP_PRICE_MIN, max(SHOP_PRICE_MIN, world.options.shop_custom_price.value)
    else:
        low, high = PRICE_RANGES[mode.value]
    low_steps = max(1, -(-low // PRICE_STEP))      # rounded up: a price never goes below the range
    high_steps = high // PRICE_STEP                # rounded down: ... nor above it
    if high_steps < low_steps:
        return [high] * count
    return [world.random.randint(low_steps, high_steps) * PRICE_STEP for _ in range(count)]
