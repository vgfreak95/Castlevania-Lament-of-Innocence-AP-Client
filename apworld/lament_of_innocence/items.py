from typing import TYPE_CHECKING, Dict, List, Set, Tuple

from BaseClasses import Item, ItemClassification

from .data_loader import GAME_NAME, ITEMS

if TYPE_CHECKING:
    from . import LoIWorld

_CLASSIFICATION = {
    "progression": ItemClassification.progression,
    "useful": ItemClassification.useful,
    "filler": ItemClassification.filler,
    "trap": ItemClassification.trap,
}

ITEM_TABLE: Dict[str, dict] = {rec["name"]: rec for rec in ITEMS}
ITEM_NAME_TO_ID: Dict[str, int] = {rec["name"]: rec["ap_id"] for rec in ITEMS}
FILLER_WEIGHTS: Dict[str, int] = {rec["name"]: rec["filler_weight"]
                                  for rec in ITEMS if rec["filler_weight"] > 0}
DEFAULT_FILLER = "Potion"

# Area Keys: hub area region -> its key, in the game's order (src/stagekeys.h: bit i of
# AP_STATUS->area_locks = entry i). StartingArea's option values 0-4 follow the same order.
AREA_KEYS: Dict[str, str] = {
    "HoSR": "Sacred Remains Key",
    "ASML": "Mystery Lab Key",
    "DPoW": "Waterfall Palace Key",
    "GFbT": "Forgotten Garden Key",
    "Theatre": "Ghostly Theatre Key",
}

# Whip skills, in the game's bit order (src/skills.h: bit i = game_id 512 + i). Never learned from
# kills in AP; Basic Skills decides Quick Step and Perfect Guard.
SKILLS: List[str] = [
    "Extension", "Draw Up", "Vertical High", "Rising Shot", "Fast Rising", "Spinning Blast",
    "Energy Blast", "Sonic Edge", "A Extension 1", "A Extension 2", "Step Attack", "Falcon Claw",
    "Quick Step", "Quick Step 2", "Perfect Guard",
]
BASIC_SKILLS = ("Quick Step", "Perfect Guard")
# AP_STATUS->skill_vanilla for Basic Skills = vanilla: the bits the game may still learn itself
BASIC_SKILLS_MASK = sum(1 << SKILLS.index(name) for name in BASIC_SKILLS)

# Progressive items: one per tier, the nth received gives the nth tier. The client maps them to the
# tiers' game IDs (game_interface.py PROGRESSIVE_TIERS, by game_id), so the game never sees them.
PROGRESSIVE: Dict[str, List[str]] = {
    "Progressive Brooch": ["Heart Brooch", "Mobius's Brooch"],
    "Progressive Plate": ["Earth Plate", "Meteor Plate", "Moonlight Plate", "Solar Plate"],
}


# Traps (src/traps.h, game_id 0x210 + n): only ever replace filler, Trap Chance percent of it.
# Trap name -> its weight option (options.py).
TRAPS: Dict[str, str] = {
    "Paralysis Trap": "paralysis_trap_weight",
    "Curse Trap": "curse_trap_weight",
    "Stone Trap": "stone_trap_weight",
    "Knockback Trap": "knockback_trap_weight",
    "Poison Trap": "poison_trap_weight",
}

ITEM_GROUPS: Dict[str, Set[str]] = {
    "Skills": set(SKILLS),
    "Traps": set(TRAPS),
    "Plates": {"Earth Plate", "Meteor Plate", "Moonlight Plate", "Solar Plate", "Progressive Plate"},
    "Brooches": {"Heart Brooch", "Mobius's Brooch", "Progressive Brooch"},
    "Area Keys": set(AREA_KEYS.values()),
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


# Given at the start instead of placed (none at the moment). The Svarog Statue used to be: the
# Prelude's tutorial Golden Knight only took its flames, until the Archipelago patch gave the
# knight the normal Golden Knight's hit handler (config.toml pokes, 0x5506AC), so now it's
# shuffled like any relic. Start inventory reaches the game through the client like any
# received item.
STARTING_ITEMS: Tuple[str, ...] = ()


def pick_starting_area_keys(world: "LoIWorld") -> List[str]:
    """The area keys the slot starts with (Area Keys on): the Starting Area's, then random
    others up to Starting Area Keys (0: none)."""
    if world.options.starting_area_keys.value == 0:
        return []
    keys = list(AREA_KEYS.values())
    first = keys[world.options.starting_area.value]   # "random" is resolved by Archipelago
    others = [k for k in keys if k != first]
    world.random.shuffle(others)
    return [first] + others[:world.options.starting_area_keys.value - 1]


def create_all_items(world: "LoIWorld") -> None:
    pool: List[LoIItem] = []
    area_keys = set(AREA_KEYS.values())
    basic = world.options.basic_skills
    progressive = [name for name, on in (("Progressive Brooch", world.options.progressive_brooch),
                                         ("Progressive Plate", world.options.progressive_plates))
                   if on]
    replaced = {tier for name in progressive for tier in PROGRESSIVE[name]}
    start = list(STARTING_ITEMS) + world.starting_area_keys
    if basic == basic.option_start_with:
        start += BASIC_SKILLS
    for name in start:
        world.multiworld.push_precollected(create_item(world, name))
    for rec in ITEMS:
        if rec["name"] in area_keys and not world.options.area_keys:
            continue                     # Area Keys off: the areas are open, no keys exist
        if rec["name"] in BASIC_SKILLS and basic == basic.option_vanilla:
            continue                     # learned the normal way (AP_STATUS->skill_vanilla)
        if rec["name"] in replaced:
            continue                     # comes as a progressive item instead
        for _ in range(rec["count"] - start.count(rec["name"])):
            pool.append(create_item(world, rec["name"]))
    for name in progressive:
        pool += [create_item(world, name) for _ in PROGRESSIVE[name]]
    unfilled = len(world.multiworld.get_unfilled_locations(world.player))
    if len(pool) > unfilled:
        raise Exception(f"{GAME_NAME}: {len(pool)} pool items for {unfilled} locations")
    traps = list(TRAPS)
    trap_weights = [getattr(world.options, TRAPS[name]).value for name in traps]
    trap_chance = world.options.trap_chance.value if any(trap_weights) else 0
    while len(pool) < unfilled:
        if world.random.randrange(100) < trap_chance:
            name = world.random.choices(traps, weights=trap_weights)[0]
        else:
            name = get_filler_item_name(world)
        pool.append(create_item(world, name))
    world.multiworld.itempool += pool
