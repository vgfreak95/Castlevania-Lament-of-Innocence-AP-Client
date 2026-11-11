from typing import TYPE_CHECKING, Dict, List, Set

from BaseClasses import Item, ItemClassification

from .data_loader import GAME_NAME, ITEMS

if TYPE_CHECKING:
    from . import LoIWorld

_CLASSIFICATION = {
    "progression": ItemClassification.progression,
    "useful": ItemClassification.useful,
    "filler": ItemClassification.filler,
}

ITEM_TABLE: Dict[str, dict] = {rec["name"]: rec for rec in ITEMS}
ITEM_NAME_TO_ID: Dict[str, int] = {rec["name"]: rec["ap_id"] for rec in ITEMS}
FILLER_WEIGHTS: Dict[str, int] = {rec["name"]: rec["filler_weight"]
                                  for rec in ITEMS if rec["filler_weight"] > 0}
DEFAULT_FILLER = "Potion"

ITEM_GROUPS: Dict[str, Set[str]] = {
    "Whips": {"Whip of Flames", "Whip of Ice", "Whip of Lightning", "Vampire Killer"},
    "Keys": {"White Tiger Key", "Blue Dragon Key", "Red Phoenix Key", "Black Turtle Key",
             "Yellow Dragon Key"},
    "Orbs": {"Red Orb", "Blue Orb", "Yellow Orb", "Green Orb", "Purple Orb", "White Orb",
             "Black Orb"},
    "Tablets": {"e Tablet", "VI Tablet", "IV Tablet"},
    "Max Ups": {"HP Max Up", "Heart Max Up", "MP Max Up"},
}


class LoIItem(Item):
    game = GAME_NAME


def create_item(world: "LoIWorld", name: str) -> LoIItem:
    rec = ITEM_TABLE[name]
    return LoIItem(name, _CLASSIFICATION[rec["classification"]], rec["ap_id"], world.player)


def create_event(world: "LoIWorld", name: str) -> LoIItem:
    return LoIItem(name, ItemClassification.progression, None, world.player)


def get_filler_item_name(world: "LoIWorld") -> str:
    names = list(FILLER_WEIGHTS)
    return world.random.choices(names, weights=[FILLER_WEIGHTS[n] for n in names])[0]


# Given at the start instead of placed: the Prelude's Golden Knight (the tutorial fight) can't be
# beaten without the Svarog Statue. Start inventory reaches the game through the client like any
# received item.
STARTING_ITEMS = ("Svarog Statue",)


def create_all_items(world: "LoIWorld") -> None:
    pool: List[LoIItem] = []
    for name in STARTING_ITEMS:
        world.multiworld.push_precollected(create_item(world, name))
    for rec in ITEMS:
        for _ in range(rec["count"] - STARTING_ITEMS.count(rec["name"])):
            pool.append(create_item(world, rec["name"]))
    unfilled = len(world.multiworld.get_unfilled_locations(world.player))
    if len(pool) > unfilled:
        raise Exception(f"{GAME_NAME}: {len(pool)} pool items for {unfilled} locations")
    while len(pool) < unfilled:
        pool.append(create_item(world, get_filler_item_name(world)))
    world.multiworld.itempool += pool
