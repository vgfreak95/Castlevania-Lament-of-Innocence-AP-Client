"""Archipelago world for Castlevania: Lament of Innocence (PS2, SLUS-20733).

The game runs on a vanilla ISO with runtime pnach patches (src/pickup.c): every item comes from
the server, and picking up a placed item only reports a location check.
"""
import logging
from typing import Any, Dict, List, TextIO

from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld, World

from .data_loader import BASE_ID, GAME_NAME, LOCATIONS
from .items import (ITEM_GROUPS, ITEM_NAME_TO_ID, LoIItem, create_all_items,
                    create_item, get_filler_item_name, pick_starting_area_keys)
from .locations import LOCATION_GROUPS, LOCATION_NAME_TO_ID
from .options import LoIOptions, option_groups
from .regions import create_regions
from .shop import (SHOP_BASE_ID, SHOP_PRICE_MIN, SHOP_VANILLA_ALL, roll_prices, shop_location_name,
                   slot_count, vanilla_mask)

logger = logging.getLogger(GAME_NAME)


class LoIWeb(WebWorld):
    theme = "stone"
    option_groups = option_groups
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up Castlevania: Lament of Innocence for Archipelago.",
        "English",
        "setup_en.md",
        "setup/en",
        ["LoI AP contributors"],
    )]


class LoIWorld(World):
    """Castlevania: Lament of Innocence (PS2). Leon Belmont storms Walter Bernhard's castle to
    rescue Sara. Every pickup and boss reward is a check; items arrive from the multiworld."""
    game = GAME_NAME
    web = LoIWeb()
    options_dataclass = LoIOptions
    options: LoIOptions
    topology_present = True
    starting_area_keys: List[str]   # set in generate_early
    shop_slot_count: int            # Shop Sanity: AP slots in Rinaldo's shop (0 = off)
    shop_prices: List[int]          # gold per shop slot

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID
    item_name_groups = ITEM_GROUPS
    location_name_groups = LOCATION_GROUPS

    def generate_early(self) -> None:
        opt = self.options.enemy_drop_sanity
        if opt.value:
            logger.warning(f"{self.player_name}: {opt.display_name} is not implemented yet; ignored.")
            opt.value = 0
        # Area Keys: the keys given at the start (the rest go in the pool)
        self.starting_area_keys = pick_starting_area_keys(self) if self.options.area_keys else []
        # Shop Sanity: the slots (35 - vanilla items kept) and their prices
        self.shop_slot_count = slot_count(self)
        self.shop_prices = roll_prices(self, self.shop_slot_count)

    def create_regions(self) -> None:
        create_regions(self)

    def create_items(self) -> None:
        create_all_items(self)

    def create_item(self, name: str) -> LoIItem:
        return create_item(self, name)

    def get_filler_item_name(self) -> str:
        return get_filler_item_name(self)

    def write_spoiler(self, spoiler_handle: TextIO) -> None:
        if not self.shop_slot_count:
            return
        spoiler_handle.write(f"\n{self.player_name}'s Rinaldo's Shop prices:\n")
        for i, price in enumerate(self.shop_prices):
            spoiler_handle.write(f"  {shop_location_name(i)}: {max(SHOP_PRICE_MIN, price)} gold\n")

    def fill_slot_data(self) -> Dict[str, Any]:
        return {
            "base_id": BASE_ID,
            **self.options.as_dict("goal", "death_link", "area_keys", "basic_skills",
                                   "progressive_brooch", "progressive_plates", "wolfs_foot_qol",
                                   "torch_sanity"),
            "shop_sanity": int(bool(self.options.shop_sanity)),
            "shop_vanilla": vanilla_mask(self) if self.options.shop_sanity else SHOP_VANILLA_ALL,
            "shop_locations": [SHOP_BASE_ID + i for i in range(self.shop_slot_count)],
            "shop_prices": list(self.shop_prices),
        }


# ---- Launcher component ------------------------------------------------------------------
# CLIENT AGENT: this is your spot. client.py must provide `launch_client(*args)`; adjust the
# names below as needed. The block is guarded so the world still loads without client.py.
def _register_client() -> None:
    import importlib.util
    try:
        if importlib.util.find_spec(f"{__name__}.client") is None:
            return
        from worlds.LauncherComponents import Component, Type, components, launch_subprocess
    except Exception:
        return

    def run_client(*args: str) -> None:
        from .client import launch_client
        launch_subprocess(launch_client, name="LamentOfInnocenceClient", args=(args,))

    components.append(Component("Lament of Innocence Client", func=run_client,
                                component_type=Type.CLIENT))


_register_client()
