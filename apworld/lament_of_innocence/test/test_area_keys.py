from . import LoITestBase
from ..data_loader import LOCATIONS
from ..items import AREA_KEYS

KEYS = list(AREA_KEYS.values())
# one location per area that needs nothing but the area itself
AREA_LOCATION = {"HoSR": "HoSR: Potion 1", "ASML": "ASML: Potion (Near Megingjord)",
                 "DPoW": "DPoW: Potion", "GFbT": "GFbT: Potion", "Theatre": "Theatre: Potion 1"}


class AreaKeysBase(LoITestBase):
    def own_pool(self):
        return [i.name for i in self.multiworld.itempool if i.player == self.player]

    def start(self):
        return [i.name for i in self.multiworld.precollected_items[self.player]]

    def test_pool_fills_locations(self) -> None:
        used = [rec for rec in LOCATIONS if rec["game_key"] is not None]
        self.assertEqual(len(self.own_pool()), len(used))


class TestChosenArea(AreaKeysBase):
    options = {"area_keys": True, "starting_area": "anti_soul_mystery_lab"}

    def test_start_with_chosen_key(self) -> None:
        start = [n for n in self.start() if n in KEYS]
        self.assertEqual(start, ["Mystery Lab Key"])
        pool = self.own_pool()
        for key in KEYS:
            self.assertEqual(pool.count(key), 0 if key == "Mystery Lab Key" else 1, key)

    def test_areas_need_keys(self) -> None:
        self.assertTrue(self.can_reach_location(AREA_LOCATION["ASML"]))
        for area, key in AREA_KEYS.items():
            if area == "ASML":
                continue
            self.assertFalse(self.can_reach_location(AREA_LOCATION[area]), area)
            self.collect_by_name(key)
            self.assertTrue(self.can_reach_location(AREA_LOCATION[area]), area)

    def test_hub_and_prison_open(self) -> None:
        self.assertTrue(self.can_reach_location("PttDA: Potion"))
        self.assertTrue(self.can_reach_location("PoET: High Potion"))


class TestSeveralStartingKeys(AreaKeysBase):
    options = {"area_keys": True, "starting_area": "ghostly_theatre", "starting_area_keys": 3}

    def test_three_keys_theatre_first(self) -> None:
        start = [n for n in self.start() if n in KEYS]
        self.assertEqual(len(start), 3)
        self.assertEqual(len(set(start)), 3)
        self.assertEqual(start[0], "Ghostly Theatre Key")
        pool = self.own_pool()
        self.assertEqual(sorted(k for k in KEYS if k in pool), sorted(set(KEYS) - set(start)))


class TestRandomArea(AreaKeysBase):
    options = {"area_keys": True, "starting_area": "random", "starting_area_keys": 5}

    def test_all_keys_at_start(self) -> None:
        self.assertEqual(sorted(n for n in self.start() if n in KEYS), sorted(KEYS))
        self.assertFalse(any(k in self.own_pool() for k in KEYS))


class TestAreaKeysOff(AreaKeysBase):
    options = {"area_keys": False}

    def test_no_keys(self) -> None:
        self.assertFalse(any(k in self.own_pool() for k in KEYS))
        self.assertFalse(any(k in self.start() for k in KEYS))
        for loc in AREA_LOCATION.values():
            self.assertTrue(self.can_reach_location(loc), loc)
