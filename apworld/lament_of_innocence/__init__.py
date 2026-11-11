"""Archipelago world for Castlevania: Lament of Innocence (PS2, SLUS-20733).

The game runs on a vanilla ISO with runtime pnach patches (src/pickup.c): every item comes from
the server, and picking up a placed item only reports a location check.
"""
import logging
from typing import Any, Dict

from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld, World

from .data_loader import BASE_ID, GAME_NAME, LOCATIONS
from .items import (ITEM_GROUPS, ITEM_NAME_TO_ID, LoIItem, create_all_items,
                    create_item, get_filler_item_name)
from .locations import LOCATION_GROUPS, LOCATION_NAME_TO_ID
from .options import LoIOptions
from .regions import create_regions

logger = logging.getLogger(GAME_NAME)


class LoIWeb(WebWorld):
    theme = "stone"
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

    item_name_to_id = ITEM_NAME_TO_ID
    location_name_to_id = LOCATION_NAME_TO_ID
    item_name_groups = ITEM_GROUPS
    location_name_groups = LOCATION_GROUPS

    def generate_early(self) -> None:
        for opt in (self.options.torch_sanity, self.options.enemy_drop_sanity):
            if opt.value:
                logger.warning(f"{self.player_name}: {opt.display_name} is not implemented yet; ignored.")
                opt.value = 0

    def create_regions(self) -> None:
        create_regions(self)

    def create_items(self) -> None:
        create_all_items(self)

    def create_item(self, name: str) -> LoIItem:
        return create_item(self, name)

    def get_filler_item_name(self) -> str:
        return get_filler_item_name(self)

    def fill_slot_data(self) -> Dict[str, Any]:
        return {
            "base_id": BASE_ID,
            **self.options.as_dict("goal", "death_link"),
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
