from . import LoITestBase
from ..data_loader import ITEMS, LOCATIONS
from ..rules import PAGODA_ORBS

AREA_BOSS_KEYS = ("e Tablet", "Curtain Time Bell")   # Golem, Succubus
WALTER_ITEMS = (*PAGODA_ORBS, *AREA_BOSS_KEYS, "Dragon Crest", "Vampire Killer")


class TestData(LoITestBase):
    def test_pool_matches_locations(self) -> None:
        # locations without a game_key (unreportable) aren't created
        used = [rec for rec in LOCATIONS if rec["game_key"] is not None]
        fixed = sum(i["count"] for i in ITEMS)
        self.assertLessEqual(fixed, len(used))
        own = [i for i in self.multiworld.itempool if i.player == self.player]
        self.assertEqual(len(own), len(used))

    def test_unique_items_once(self) -> None:
        names = [i.name for i in self.multiworld.itempool]
        for unique in ("Curtain Time Bell", "Vampire Killer", "Dragon Crest", "Red Orb",
                       "Whip of Flames", "Aroma Earring"):
            self.assertEqual(names.count(unique), 1, unique)
        self.assertNotIn("Whip of Alchemy", names)

    def test_keys_and_ids_unique(self) -> None:
        ids = [rec["ap_id"] for rec in LOCATIONS]
        keys = [rec["game_key"] for rec in LOCATIONS if rec["game_key"] is not None]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(keys), len(set(keys)))

    def test_extra_locations_only_filler(self) -> None:
        from BaseClasses import LocationProgressType
        for rec in LOCATIONS:
            if rec.get("excluded"):
                loc = self.multiworld.get_location(rec["name"], self.player)
                self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED, rec["name"])

    def test_starts_with_svarog(self) -> None:
        names = [i.name for i in self.multiworld.itempool]
        self.assertNotIn("Svarog Statue", names)
        start = [i.name for i in self.multiworld.precollected_items[self.player]]
        self.assertEqual(start.count("Svarog Statue"), 1)

    def test_ids_stable(self) -> None:
        by_name = {r["name"]: r for r in LOCATIONS}
        self.assertEqual(by_name["PttDA: Svarog Statue"]["ap_id"], 207330008)
        self.assertEqual(by_name["HoSR: Marker Stone 6"]["ap_id"], 207330009)
        self.assertEqual(by_name["PoET: High Potion"]["ap_id"], 207330111)
        self.assertEqual(by_name["ASML: Golem"]["ap_id"], 207331500)
        self.assertEqual(by_name["GFbT: Thunder Elemental"]["ap_id"], 207331508)
        self.assertEqual(len({r["ap_id"] for r in LOCATIONS}), 121 + 30)   # + extra_locations.json
        self.assertEqual(by_name["HoSR: Room 3 $25 1"]["ap_id"], 207340192)


class TestKeyDoors(LoITestBase):
    def test_key_doors(self) -> None:
        for loc, item in (("HoSR: Black Bishop", "Yellow Dragon Key"),
                          ("ASML: Wolf's Foot", "Red Phoenix Key"),
                          ("DPoW: Draupnir", "Black Turtle Key"),
                          ("GFbT: Tool Bag", "Blue Dragon Key"),
                          ("Theatre: Heart Brooch", "White Tiger Key"),
                          ("ASML: Golem", "e Tablet"),
                          ("Theatre: Succubus", "Curtain Time Bell"),
                          ("PoET: Forgotten One", "Unlock Jewel")):
            self.assertFalse(self.can_reach_location(loc), loc)
            self.collect_by_name(item)
            self.assertTrue(self.can_reach_location(loc), loc)

    def test_white_orb_needs_both_whips(self) -> None:
        self.collect_by_name("Whip of Flames")
        self.assertFalse(self.can_reach_location("ASML: White Orb"))
        self.collect_by_name("Whip of Ice")
        self.assertTrue(self.can_reach_location("ASML: White Orb"))

    def test_wolfs_foot(self) -> None:
        self.assertFalse(self.can_reach_location("ASML: Megingjord"))
        self.assertFalse(self.can_reach_location("GFbT: Saisei Incense"))
        self.collect_by_name("Wolf's Foot")
        self.assertTrue(self.can_reach_location("ASML: Megingjord"))
        self.assertTrue(self.can_reach_location("GFbT: Saisei Incense"))

    def test_open_areas(self) -> None:
        for loc in ("PttDA: Potion", "HoSR: Potion 1", "ASML: Potion (Near Megingjord)",
                    "DPoW: Potion", "GFbT: Potion", "Theatre: Potion 1", "PoET: High Potion",
                    "HoSR: Undead Parasite", "DPoW: Joachim", "GFbT: Medusa"):
            self.assertTrue(self.can_reach_location(loc), loc)


class TestPagoda(LoITestBase):
    def test_pagoda_seal(self) -> None:
        self.assertFalse(self.can_reach_region("PotMM"))
        self.collect_by_name(list(PAGODA_ORBS))
        self.assertFalse(self.can_reach_region("PotMM"))   # Golem and Succubus not beatable yet
        self.collect_by_name("e Tablet")
        self.assertFalse(self.can_reach_region("PotMM"))
        self.collect_by_name("Curtain Time Bell")
        self.assertTrue(self.can_reach_region("PotMM"))
        self.assertFalse(self.can_reach_location("PotMM: Dragon Crest"))
        self.collect_by_name("VI Tablet")
        self.assertTrue(self.can_reach_location("PotMM: Dragon Crest"))

    def test_walter(self) -> None:
        self.assertBeatable(False)
        self.collect_by_name([i for i in WALTER_ITEMS if i != "Vampire Killer"])
        self.assertBeatable(False)
        self.collect_by_name("Vampire Killer")
        self.assertBeatable(True)


class TestDeathGoal(LoITestBase):
    options = {"goal": "defeat_death"}

    def test_death(self) -> None:
        self.assertBeatable(False)
        self.collect_by_name(list(WALTER_ITEMS))
        self.assertBeatable(True)
        self.assertTrue(self.can_reach_location("Walter's Room: Death"))
