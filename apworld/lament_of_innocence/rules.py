"""Access rules, ported from the randomizer's req_table (CvLoIRandomizerV5.c 1860-1882) plus the
vanilla gates the randomizer patches out of the ISO (we run on a vanilla ISO).

Key doors were checked against the vanilla ISO: door record byte +5, + 0x58 = key id
(0x0D7F5785 -> Red Phoenix, 0x141C2585 -> Blue Dragon, 0x08A98305 -> Yellow Dragon,
0x108AA885 -> Black Turtle, 0x27915F85 -> White Tiger). The PoET boss room byte (0x1F51DD72) is
0x03 = Forgotten One, so the Unlock Jewel gates the Forgotten One.
"""
from typing import Callable, Dict, Optional, Tuple

from BaseClasses import CollectionState

from .locations import AREA_BOSSES, boss_event_item

Rule = Callable[[CollectionState], bool]

PAGODA_ORBS = ("Red Orb", "Blue Orb", "Yellow Orb", "Green Orb", "Purple Orb")
WALTER_EVENT = "Walter Defeated"
DEATH_EVENT = "Death Defeated"

# location -> items needed (all of them)
LOCATION_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
    "HoSR: Black Bishop": ("Yellow Dragon Key",),
    "ASML: White Orb": ("Whip of Flames", "Whip of Ice"),
    "ASML: Wolf's Foot": ("Red Phoenix Key",),
    "ASML: Megingjord": ("Wolf's Foot",),
    "GFbT: Saisei Incense": ("Wolf's Foot",),
    "DPoW: Little Hammer": ("Whip of Flames",),
    "DPoW: Draupnir": ("Black Turtle Key",),
    "GFbT: Tool Bag": ("Blue Dragon Key",),
    "Theatre: Heart Brooch": ("White Tiger Key",),
    "PotMM: Dragon Crest": ("VI Tablet",),
    # VERIFY: the randomizer says it "removes lock(s) on PttDA doors to prevent Svarog Statue
    # from being required". Which vanilla PttDA doors are locked, by what, and which of the
    # PttDA locations are behind them? Modelled as no requirement.
}

# boss reward location -> items needed
BOSS_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
    "ASML: Golem": ("e Tablet",),
    # VERIFY: does the Succubus door really need the Curtain Time Bell in vanilla (randomizer
    # req_table says so)?
    "Theatre: Succubus": ("Curtain Time Bell",),
    "PoET: Forgotten One": ("Unlock Jewel",),
    "HoSR: Undead Parasite": (),   # behind a switch door, no item
    "DPoW: Joachim": (),           # behind a switch door, no item
    "GFbT: Medusa": (),
    "ASML: Flame Elemental": (),
    "DPoW: Frost Elemental": (),
    "GFbT: Thunder Elemental": (),
}


def _has_all(items: Tuple[str, ...], player: int) -> Optional[Rule]:
    if not items:
        return None
    return lambda state: state.has_all(items, player)


def location_rule(name: str, player: int) -> Optional[Rule]:
    return _has_all(LOCATION_REQUIREMENTS.get(name, ()), player)


def boss_rule(name: str, player: int) -> Optional[Rule]:
    return _has_all(BOSS_REQUIREMENTS[name], player)


def pagoda_seal(state: CollectionState, player: int) -> bool:
    return (state.has_all(PAGODA_ORBS, player)
            and state.has_all([boss_event_item(b) for b in AREA_BOSSES], player))


def walter_stairs(state: CollectionState, player: int) -> bool:
    # Randomizer final-boss rule (line 1972): Vampire Killer, Dragon Crest and the five orbs.
    # The orbs are already needed for the Pagoda.
    # VERIFY: does the Dragon Crest open the stairs to Walter in vanilla, and is Vampire Killer
    # really required (vanilla boss reward slot 11 holds Vampire Killer: is it handed out by a
    # story event that still runs with the runtime patch)?
    return state.has_all(("Vampire Killer", "Dragon Crest"), player)
