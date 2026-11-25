from BaseClasses import ItemClassification, LocationProgressType

from . import LoITestBase
from ..data_loader import LOCATIONS, TORCHES
from ..rules import GATED_ROOMS, ROOM_REQUIREMENTS, torch_rule

TORCH_NAMES = {rec["name"] for rec in TORCHES}


class TorchBase(LoITestBase):
    def torch_locations(self):
        return [loc for loc in self.multiworld.get_locations(self.player) if loc.name in TORCH_NAMES]

    def own_pool(self):
        return [i for i in self.multiworld.itempool if i.player == self.player]


class TestTorchesOff(TorchBase):
    def test_no_torch_locations(self) -> None:
        self.assertEqual(self.torch_locations(), [])


class TestTorchesFillerOnly(TorchBase):
    options = {"area_keys": False, "torch_sanity": "filler_only"}

    def test_every_torch_is_a_location(self) -> None:
        self.assertEqual(len(self.torch_locations()), len(TORCHES))

    def test_pool_fills_locations(self) -> None:
        used = [rec for rec in LOCATIONS if rec["game_key"] is not None]
        self.assertEqual(len(self.own_pool()), len(used) + len(TORCHES))

    def test_torches_only_hold_filler(self) -> None:
        for loc in self.torch_locations():
            self.assertEqual(loc.progress_type, LocationProgressType.EXCLUDED, loc.name)
            if loc.item is not None and loc.item.player == self.player:
                self.assertFalse(loc.item.classification & (ItemClassification.progression
                                                            | ItemClassification.useful), loc.name)

    def test_slot_data(self) -> None:
        self.assertEqual(self.world.fill_slot_data()["torch_sanity"], 1)


class TestTorchesFull(TorchBase):
    options = {"area_keys": False, "torch_sanity": "full"}

    def test_every_torch_is_a_location(self) -> None:
        locs = self.torch_locations()
        self.assertEqual(len(locs), len(TORCHES))
        self.assertTrue(all(loc.progress_type == LocationProgressType.DEFAULT for loc in locs))

    def test_room_locks_apply(self) -> None:
        """A torch in a room with a gated pickup would need the same items. (In the current data
        no torch shares a room with one: the key-door rooms hold only their item.)"""
        self.assertTrue(ROOM_REQUIREMENTS)
        room, needed = next(iter(ROOM_REQUIREMENTS.items()))
        rule = torch_rule({"room_key": room}, self.player)
        self.assertIsNotNone(rule)
        state = self.multiworld.get_all_state(False)
        self.assertTrue(rule(state))
        state.remove(self.world.create_item(needed[0]))
        self.assertFalse(rule(state))
        self.assertIsNone(torch_rule({"room_key": -1}, self.player))

    def test_gated_rooms(self) -> None:
        """GFbT rooms 52 and 53 (before Saisei Incense) need Wolf's Foot; room 49 doesn't."""
        state = self.multiworld.get_all_state(False)
        without = self.multiworld.get_all_state(False)
        without.remove(self.world.create_item("Wolf's Foot"))
        for (stage, room) in GATED_ROOMS:
            torches = [rec for rec in TORCHES if rec["stage"] == stage and rec["room"] == room]
            self.assertTrue(torches, f"no torches in stage {stage} room {room}")
            for rec in torches:
                loc = self.multiworld.get_location(rec["name"], self.player)
                self.assertTrue(loc.can_reach(state), rec["name"])
                self.assertFalse(loc.access_rule(without), rec["name"])
        for rec in TORCHES:
            if rec["stage"] == 3 and rec["room"] == 49:
                loc = self.multiworld.get_location(rec["name"], self.player)
                self.assertTrue(loc.access_rule(without), rec["name"])
