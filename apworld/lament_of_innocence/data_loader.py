"""Loads data/locations.json and data/items.json. Works from a folder and from a zipped .apworld."""
import json
import pkgutil
from typing import Any, Dict, List

GAME_NAME = "Castlevania - Lament of Innocence"
BASE_ID = 207330000   # SLUS-207.33. location ap_id = BASE + Location_list index; item = BASE + game id


def _load(name: str) -> List[Dict[str, Any]]:
    raw = pkgutil.get_data(__package__ or __name__.rpartition(".")[0], f"data/{name}")
    if raw is None:
        raise FileNotFoundError(name)
    return json.loads(raw.decode("utf-8"))


# locations.json: the randomizer's locations (tools/loc_scan.py fills their game_key).
# extra_locations.json: placed pickups the location scan found that the randomizer doesn't have
# (ap_id = EXTRA_BASE_ID + game_key); "excluded" ones never hold progression or useful items.
EXTRA_BASE_ID = 207340000
LOCATIONS: List[Dict[str, Any]] = _load("locations.json") + _load("extra_locations.json")
ITEMS: List[Dict[str, Any]] = _load("items.json")
