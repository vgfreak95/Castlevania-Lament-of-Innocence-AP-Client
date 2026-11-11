"""Regions. The game runs on a vanilla ISO with runtime patches (src/pickup.c), so every vanilla
progression gate is still in place: key doors, boss doors, the Pagoda seal, Walter's stairs.

Menu -> PttDA (Prelude / Warp Room) -> HoSR, ASML, DPoW, GFbT, Theatre, PoET
                                    -> PotMM (seal: 5 orbs + 5 area bosses) -> Walter's Room
"""
from typing import TYPE_CHECKING, Callable, Dict, Optional

from BaseClasses import CollectionState, LocationProgressType, Region

from .data_loader import LOCATIONS
from .items import create_event
from .locations import AREA_BOSSES, BOSS_REGION, LoILocation, boss_event_item
from .rules import DEATH_EVENT, WALTER_EVENT, boss_rule, location_rule, pagoda_seal, walter_stairs

if TYPE_CHECKING:
    from . import LoIWorld

AREAS = ["PttDA", "HoSR", "ASML", "DPoW", "GFbT", "Theatre", "PotMM", "PoET"]
WALTERS_ROOM = "Walter's Room"


def create_regions(world: "LoIWorld") -> None:
    mw, player = world.multiworld, world.player
    regions: Dict[str, Region] = {}
    for name in ["Menu", *AREAS, WALTERS_ROOM]:
        regions[name] = Region(name, player, mw)
        mw.regions.append(regions[name])

    def connect(src: str, dst: str, rule: Optional[Callable[[CollectionState], bool]] = None):
        regions[src].connect(regions[dst], f"{src} -> {dst}", rule)

    connect("Menu", "PttDA")
    # VERIFY: are all five areas (HoSR, ASML, DPoW, GFbT, Theatre) open from the Warp Room at
    # the start of a vanilla game, with no item or boss needed?
    for area in ["HoSR", "ASML", "DPoW", "GFbT", "Theatre"]:
        connect("PttDA", area)
    # VERIFY: is the Prison of Eternal Torture reachable from the start? The randomizer gives its
    # High Potion no requirement and only puts the Unlock Jewel on the boss door inside.
    connect("PttDA", "PoET")
    # VERIFY: the Pagoda seal (door record ISO 0x1F9EF280, lock byte 0x08, patched out by the
    # randomizer). Does it check the five orbs in the inventory, or the five area bosses'
    # defeat flags? Modelled conservatively as both.
    connect("PttDA", "PotMM", lambda state: pagoda_seal(state, player))
    connect("PotMM", WALTERS_ROOM, lambda state: walter_stairs(state, player))

    # item locations; ones the game patch can't report (no game_key from the location scan, e.g.
    # the respawning bowling Ramen) are left out, or nothing could ever check them
    for rec in LOCATIONS:
        if rec["game_key"] is None:
            continue
        loc = LoILocation(player, rec["name"], rec["ap_id"], regions[rec["region"]])
        rule = boss_rule(rec["name"], player) if rec["kind"] == "boss" else location_rule(rec["name"], player)
        if rule is not None:
            loc.access_rule = rule
        if rec.get("excluded"):
            # VERIFY: the extra money pickups' rooms may be behind doors the logic doesn't know
            # about, so they only get filler until that's checked
            loc.progress_type = LocationProgressType.EXCLUDED
        regions[rec["region"]].locations.append(loc)

    # boss-defeat events for the Pagoda seal
    for boss in AREA_BOSSES:
        region = regions[BOSS_REGION[boss]]
        ev = LoILocation(player, f"{BOSS_REGION[boss]}: {boss} (Event)", None, region)
        rule = boss_rule(f"{BOSS_REGION[boss]}: {boss}", player)
        if rule is not None:
            ev.access_rule = rule
        ev.place_locked_item(create_event(world, boss_event_item(boss)))
        region.locations.append(ev)

    # goal events. VERIFY: Death is fought right after Walter, with nothing extra needed.
    walter = LoILocation(player, "Walter's Room: Walter", None, regions[WALTERS_ROOM])
    walter.place_locked_item(create_event(world, WALTER_EVENT))
    regions[WALTERS_ROOM].locations.append(walter)
    death = LoILocation(player, "Walter's Room: Death", None, regions[WALTERS_ROOM])
    death.access_rule = lambda state: state.has(WALTER_EVENT, player)
    death.place_locked_item(create_event(world, DEATH_EVENT))
    regions[WALTERS_ROOM].locations.append(death)

    goal_event = DEATH_EVENT if world.options.goal == world.options.goal.option_defeat_death else WALTER_EVENT
    mw.completion_condition[player] = lambda state: state.has(goal_event, player)

