from . import LoITestBase
from ..data_loader import BASE_ID, EXTRA_BASE_ID, LOCATIONS, TORCH_BASE_ID, TORCHES
from ..locations import LOCATION_GROUPS
from ..shop import (PRICE_RANGES, SHOP_BASE_ID, SHOP_REGION, SHOP_SLOTS_MAX, SHOP_VANILLA,
                    SHOP_VANILLA_ALL, shop_location_name)

SHOP_NAMES = {shop_location_name(i) for i in range(SHOP_SLOTS_MAX)}
USED_LOCATIONS = [rec for rec in LOCATIONS if rec["game_key"] is not None]


class ShopBase(LoITestBase):
    def shop_locations(self):
        return [loc for loc in self.multiworld.get_locations(self.player) if loc.name in SHOP_NAMES]

    def own_pool(self):
        return [i for i in self.multiworld.itempool if i.player == self.player]

    def slot_data(self):
        return self.world.fill_slot_data()


class TestShopDatapackage(ShopBase):
    def test_every_slot_has_a_stable_id(self) -> None:
        ids = self.world.location_name_to_id
        for i in range(SHOP_SLOTS_MAX):
            self.assertEqual(ids[shop_location_name(i)], SHOP_BASE_ID + i)
        self.assertEqual(shop_location_name(0), "Rinaldo's Shop: Item 1")
        self.assertEqual(shop_location_name(63), "Rinaldo's Shop: Item 64")
        self.assertEqual(LOCATION_GROUPS["Shop"], SHOP_NAMES)

    def test_ids_collide_with_nothing(self) -> None:
        others = {rec["ap_id"] for rec in LOCATIONS + TORCHES}
        shop = set(range(SHOP_BASE_ID, SHOP_BASE_ID + SHOP_SLOTS_MAX))
        self.assertFalse(others & shop)
        self.assertEqual(len(set(self.world.location_name_to_id.values())),
                         len(self.world.location_name_to_id))
        # the id blocks the other kinds can ever use stay below the shop's
        self.assertLess(EXTRA_BASE_ID + 0x8000, SHOP_BASE_ID)
        self.assertLess(TORCH_BASE_ID + 1536, SHOP_BASE_ID)
        self.assertLess(BASE_ID + 1509, SHOP_BASE_ID)

    def test_vanilla_order_matches_client(self) -> None:
        from ..game_interface import SHOP_KEY_BASE, SHOP_VANILLA_ITEMS
        from ..game_interface import SHOP_SLOTS_MAX as GI_SLOTS_MAX
        from ..game_interface import SHOP_VANILLA_ALL as GI_ALL
        from .. import shop
        self.assertEqual([n for n, _ in SHOP_VANILLA], [n for n, _ in SHOP_VANILLA_ITEMS])
        self.assertEqual(SHOP_VANILLA_ALL, GI_ALL)
        self.assertEqual(SHOP_SLOTS_MAX, GI_SLOTS_MAX)
        self.assertEqual(shop.SHOP_KEY_BASE, SHOP_KEY_BASE)


class TestShopOff(ShopBase):
    def test_no_shop_locations(self) -> None:
        self.assertEqual(self.shop_locations(), [])

    def test_slot_data(self) -> None:
        data = self.slot_data()
        self.assertEqual(data["shop_sanity"], 0)
        self.assertEqual(data["shop_vanilla"], SHOP_VANILLA_ALL)
        self.assertEqual(data["shop_locations"], [])
        self.assertEqual(data["shop_prices"], [])


class TestShopAllVanillaKept(ShopBase):
    options = {"area_keys": False, "shop_sanity": True}

    def test_twenty_slots(self) -> None:
        locs = self.shop_locations()
        self.assertEqual(len(locs), 20)
        self.assertEqual({loc.name for loc in locs}, {shop_location_name(i) for i in range(20)})
        self.assertTrue(all(loc.parent_region.name == SHOP_REGION for loc in locs))

    def test_pool_fills_locations(self) -> None:
        self.assertEqual(len(self.own_pool()), len(USED_LOCATIONS) + 20)

    def test_slots_need_only_the_shop(self) -> None:
        state = self.multiworld.state.copy()   # nothing collected beyond the start inventory
        for loc in self.shop_locations():
            self.assertTrue(loc.can_reach(state), loc.name)

    def test_slot_data(self) -> None:
        data = self.slot_data()
        self.assertEqual(data["shop_sanity"], 1)
        self.assertEqual(data["shop_vanilla"], SHOP_VANILLA_ALL)
        self.assertEqual(data["shop_locations"], [SHOP_BASE_ID + i for i in range(20)])
        self.assertEqual(len(data["shop_prices"]), 20)
        for loc_id in data["shop_locations"]:
            self.assertIsNotNone(self.multiworld.get_location(
                self.world.location_id_to_name[loc_id], self.player))

    def test_normal_prices(self) -> None:
        low, high = PRICE_RANGES[2]
        self.assertTrue(all(low <= p <= high and p % 10 == 0 for p in self.slot_data()["shop_prices"]))


class TestShopSomeRemoved(ShopBase):
    # Potion, Diamond, Music Box and White Bishop off: 35 - 11 = 24 slots
    options = {"area_keys": False, "shop_sanity": True, "shop_potion": False, "shop_diamond": False,
               "shop_music_box": False, "shop_white_bishop": False}

    def test_slot_count(self) -> None:
        self.assertEqual(len(self.shop_locations()), 24)
        self.assertEqual(len(self.own_pool()), len(USED_LOCATIONS) + 24)

    def test_slot_data(self) -> None:
        data = self.slot_data()
        expected = SHOP_VANILLA_ALL & ~(1 << 0 | 1 << 6 | 1 << 12 | 1 << 14)
        self.assertEqual(data["shop_vanilla"], expected)
        self.assertEqual(data["shop_locations"], [SHOP_BASE_ID + i for i in range(24)])
        self.assertEqual(len(data["shop_prices"]), 24)


class TestShopNoneKept(ShopBase):
    options = {"area_keys": False, "shop_sanity": True, "shop_prices": "unaffordable",
               **{opt: False for _, opt in SHOP_VANILLA}}

    def test_thirty_five_slots(self) -> None:
        self.assertEqual(len(self.shop_locations()), 35)
        self.assertEqual(self.slot_data()["shop_vanilla"], 0)

    def test_unaffordable_prices(self) -> None:
        prices = self.slot_data()["shop_prices"]
        self.assertEqual(len(prices), 35)
        self.assertTrue(all(1000 <= p <= 5000 and p % 10 == 0 for p in prices))


class TestShopAffordable(ShopBase):
    options = {"area_keys": False, "shop_sanity": True, "shop_prices": "affordable"}

    def test_prices(self) -> None:
        self.assertTrue(all(10 <= p <= 500 and p % 10 == 0 for p in self.slot_data()["shop_prices"]))


class TestShopCustomPrice(ShopBase):
    options = {"area_keys": False, "shop_sanity": True, "shop_prices": "custom",
               "shop_custom_price": 1234}

    def test_prices(self) -> None:
        prices = self.slot_data()["shop_prices"]
        self.assertEqual(len(prices), 20)
        self.assertTrue(all(10 <= p <= 1230 and p % 10 == 0 for p in prices), prices)
        self.assertGreater(len(set(prices)), 1)                 # rolled, not one fixed price


class TestShopCustomPriceMin(ShopBase):
    options = {"area_keys": False, "shop_sanity": True, "shop_prices": "custom",
               "shop_custom_price": 2}

    def test_prices(self) -> None:
        self.assertEqual(self.slot_data()["shop_prices"], [2] * 20)


class TestShopNoKeptItemsInSlots(ShopBase):
    """Slots never hold this world's copy of an item still on sale; removed ones may."""
    options = {"area_keys": False, "shop_sanity": True, "shop_potion": False, "trap_chance": 0}

    def test_no_kept_items(self) -> None:
        from Fill import distribute_items_restrictive
        from worlds.AutoWorld import call_all
        from ..shop import SHOP_VANILLA
        kept = {name for name, opt in SHOP_VANILLA if opt != "shop_potion"}
        call_all(self.multiworld, "pre_fill")
        distribute_items_restrictive(self.multiworld)
        for loc in self.shop_locations():
            item = loc.item
            self.assertFalse(item.player == self.player and item.name in kept, (loc.name, item.name))

    def test_rule(self) -> None:
        loc = self.shop_locations()[0]
        self.assertFalse(loc.item_rule(self.world.create_item("High Potion")))
        self.assertTrue(loc.item_rule(self.world.create_item("Potion")))   # off sale: allowed


class TestShopWithAreaKeysAndTorches(ShopBase):
    """Shop Sanity together with the other location options and traps: generation fills it all."""
    options = {"area_keys": True, "starting_area_keys": 0, "shop_sanity": True,
               "torch_sanity": "full", "trap_chance": 50, "shop_zircon": False}

    def test_counts(self) -> None:
        self.assertEqual(len(self.shop_locations()), 21)
        self.assertEqual(len(self.own_pool()), len(USED_LOCATIONS) + len(TORCHES) + 21)
