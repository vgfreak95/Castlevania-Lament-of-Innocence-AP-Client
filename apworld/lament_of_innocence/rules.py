"""Access rules, ported from the randomizer's req_table (CvLoIRandomizerV5.c 1860-1882) plus the
vanilla gates the randomizer patches out of the ISO (we run on a vanilla ISO).

Key doors were checked against the vanilla ISO: door record byte +5, + 0x58 = key id
(0x0D7F5785 -> Red Phoenix, 0x141C2585 -> Blue Dragon, 0x08A98305 -> Yellow Dragon,
0x108AA885 -> Black Turtle, 0x27915F85 -> White Tiger). The PoET boss room byte (0x1F51DD72) is
0x03 = Forgotten One, so the Unlock Jewel gates the Forgotten One.
"""
from typing import Callable, Dict, Optional, Tuple

from BaseClasses import CollectionState

from .locations import AREA_BOSSES, LOCATION_TABLE, boss_event_item

BOSS_KEY_BASE = 0x8000   # boss reward game_key = BOSS_KEY_BASE + index (src/ap.h)

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


def _room_requirements() -> Dict[int, Tuple[str, ...]]:
    """room key -> every item the gated pickups of that room need (a pickup's game_key is
    room_key * 64 + flag index; boss rewards have no room)."""
    rooms: Dict[int, Tuple[str, ...]] = {}
    for name, items in LOCATION_REQUIREMENTS.items():
        rec = LOCATION_TABLE.get(name)
        if not rec or rec.get("game_key") is None or rec["game_key"] >= BOSS_KEY_BASE:
            continue
        room = rec["game_key"] // 64
        rooms[room] = tuple(sorted(set(rooms.get(room, ())) | set(items)))
    return rooms


ROOM_REQUIREMENTS: Dict[int, Tuple[str, ...]] = _room_requirements()

# Rooms behind an in-area gate, (stage, room) -> items needed to get in: what the area's region
# rule doesn't cover. Torch Sanity "full" applies them to the torches in those rooms. Add rooms
# here as the gates are mapped (stage/room as the debug menu's Info HUD shows them).
GATED_ROOMS: Dict[Tuple[int, int], Tuple[str, ...]] = {
    # GFbT: the Wolf's Foot jump in room 49 leads to the torch room 52 and the torch hallway 53,
    # then Saisei Incense (room 54, "GFbT: Saisei Incense" above)
    (3, 52): ("Wolf's Foot",),
    (3, 53): ("Wolf's Foot",),
}


def torch_rule(rec: dict, player: int) -> Optional[Rule]:
    """Torch Sanity "full": a torch needs what its room's gate needs (GATED_ROOMS) plus what the
    gated pickups of its room need.
    VERIFY: only the rooms in GATED_ROOMS are known; a torch in any other room behind an in-area
    gate (key door, Wolf's Foot jump, elemental whip, breakable wall, switch door) counts as open
    once its area is reached."""
    items = set(GATED_ROOMS.get((rec.get("stage"), rec.get("room")), ()))
    items |= set(ROOM_REQUIREMENTS.get(rec["room_key"], ()))
    return _has_all(tuple(sorted(items)), player)


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
