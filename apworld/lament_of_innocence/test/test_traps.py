from BaseClasses import ItemClassification

from . import LoITestBase
from ..data_loader import LOCATIONS
from ..items import ITEM_TABLE, TRAPS


class TrapsBase(LoITestBase):
    def own_pool(self):
        return [i for i in self.multiworld.itempool if i.player == self.player]

    def traps_in_pool(self):
        return [i.name for i in self.own_pool() if i.name in TRAPS]

    def test_pool_fills_locations(self) -> None:
        used = [rec for rec in LOCATIONS if rec["game_key"] is not None]
        self.assertEqual(len(self.own_pool()), len(used))


class TestTrapData(LoITestBase):
    def test_game_ids(self) -> None:
        # src/traps.h: TRAP_ITEM_BASE 0x210, in enum order
        for n, name in enumerate(TRAPS):
            self.assertEqual(ITEM_TABLE[name]["game_id"], 0x210 + n, name)
            self.assertEqual(ITEM_TABLE[name]["classification"], "trap", name)


class TestTrapsOffByDefault(TrapsBase):
    def test_no_traps(self) -> None:
        self.assertEqual(self.traps_in_pool(), [])


class TestTrapsAllFiller(TrapsBase):
    options = {"trap_chance": 100}

    def test_filler_all_traps(self) -> None:
        self.assertTrue(self.traps_in_pool())
        for item in self.own_pool():
            if item.name in TRAPS:
                self.assertEqual(item.classification, ItemClassification.trap)
            else:   # filler items (filler_weight > 0) are only ever added as filler
                self.assertEqual(ITEM_TABLE[item.name]["filler_weight"], 0, item.name)


class TestTrapsOnlyKnockback(TrapsBase):
    options = {"trap_chance": 100, "paralysis_trap_weight": 0, "curse_trap_weight": 0,
               "stone_trap_weight": 0, "knockback_trap_weight": 3,
               "poison_trap_weight": 0}

    def test_only_knockback(self) -> None:
        traps = self.traps_in_pool()
        self.assertTrue(traps)
        self.assertEqual(set(traps), {"Knockback Trap"})


class TestTrapsAllWeightsZero(TrapsBase):
    options = {"trap_chance": 100, "paralysis_trap_weight": 0, "curse_trap_weight": 0,
               "stone_trap_weight": 0, "knockback_trap_weight": 0,
               "poison_trap_weight": 0}

    def test_no_traps(self) -> None:
        self.assertEqual(self.traps_in_pool(), [])
