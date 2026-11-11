from typing import Dict, Set

from BaseClasses import Location

from .data_loader import GAME_NAME, LOCATIONS

LOCATION_TABLE: Dict[str, dict] = {rec["name"]: rec for rec in LOCATIONS}
LOCATION_NAME_TO_ID: Dict[str, int] = {rec["name"]: rec["ap_id"] for rec in LOCATIONS}

LOCATION_GROUPS: Dict[str, Set[str]] = {}
for _rec in LOCATIONS:
    LOCATION_GROUPS.setdefault(_rec["region"], set()).add(_rec["name"])
LOCATION_GROUPS["Bosses"] = {r["name"] for r in LOCATIONS if r["kind"] == "boss"}

# Boss-defeat events: (event location, region, event item). The event has the same rule as the
# boss's reward location (rules.py). The five area bosses open the Pagoda seal.
AREA_BOSSES = ["Undead Parasite", "Golem", "Joachim", "Medusa", "Succubus"]
BOSS_REGION = {"Undead Parasite": "HoSR", "Golem": "ASML", "Joachim": "DPoW", "Medusa": "GFbT",
               "Succubus": "Theatre"}


def boss_event_item(boss: str) -> str:
    return f"{boss} Defeated"


class LoILocation(Location):
    game = GAME_NAME
