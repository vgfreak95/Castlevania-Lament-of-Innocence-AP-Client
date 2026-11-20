from . import LoITestBase
from ..data_loader import LOCATIONS
from ..game_interface import PROGRESSIVE_TIERS
from ..items import ITEM_TABLE, PROGRESSIVE


class ProgressiveBase(LoITestBase):
    def own_pool(self):
        return [i.name for i in self.multiworld.itempool if i.player == self.player]

    def test_pool_fills_locations(self) -> None:
        used = [rec for rec in LOCATIONS if rec["game_key"] is not None]
        self.assertEqual(len(self.own_pool()), len(used))


class TestProgressiveData(LoITestBase):
    def test_client_tiers_match(self) -> None:
        # the client maps by game_id (game_interface.py); the world by name (items.py)
        for name, tiers in PROGRESSIVE.items():
            self.assertEqual(PROGRESSIVE_TIERS[ITEM_TABLE[name]["game_id"]],
                             [ITEM_TABLE[t]["game_id"] for t in tiers], name)


class TestProgressiveOff(ProgressiveBase):
    def test_tiers_in_pool(self) -> None:
        pool = self.own_pool()
        for name, tiers in PROGRESSIVE.items():
            self.assertNotIn(name, pool)
            for tier in tiers:
                self.assertEqual(pool.count(tier), 1, tier)


class TestProgressiveOn(ProgressiveBase):
    options = {"progressive_brooch": True, "progressive_plates": True}

    def test_progressive_in_pool(self) -> None:
        pool = self.own_pool()
        for name, tiers in PROGRESSIVE.items():
            self.assertEqual(pool.count(name), len(tiers), name)
            for tier in tiers:
                self.assertNotIn(tier, pool)


class TestProgressiveBroochOnly(ProgressiveBase):
    options = {"progressive_brooch": True}

    def test_only_brooch(self) -> None:
        pool = self.own_pool()
        self.assertEqual(pool.count("Progressive Brooch"), 2)
        self.assertNotIn("Progressive Plate", pool)
        self.assertEqual(pool.count("Solar Plate"), 1)
