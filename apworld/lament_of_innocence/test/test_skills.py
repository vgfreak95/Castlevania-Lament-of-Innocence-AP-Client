from . import LoITestBase
from ..data_loader import LOCATIONS
from ..items import BASIC_SKILLS, BASIC_SKILLS_MASK, ITEM_TABLE, SKILLS

OTHER_SKILLS = [s for s in SKILLS if s not in BASIC_SKILLS]


class SkillsBase(LoITestBase):
    def own_pool(self):
        return [i.name for i in self.multiworld.itempool if i.player == self.player]

    def start(self):
        return [i.name for i in self.multiworld.precollected_items[self.player]]

    def test_pool_fills_locations(self) -> None:
        used = [rec for rec in LOCATIONS if rec["game_key"] is not None]
        self.assertEqual(len(self.own_pool()), len(used))

    def test_other_skills_in_pool(self) -> None:
        pool = self.own_pool()
        for name in OTHER_SKILLS:
            self.assertEqual(pool.count(name), 1, name)


class TestSkillData(LoITestBase):
    def test_game_ids_follow_bits(self) -> None:
        # src/skills.h: skill bit i = item game_id 0x200 + i
        for bit, name in enumerate(SKILLS):
            self.assertEqual(ITEM_TABLE[name]["game_id"], 0x200 + bit, name)
        self.assertEqual(BASIC_SKILLS_MASK, 0x5000)   # client.py BASIC_SKILLS_MASK


class TestBasicSkillsVanilla(SkillsBase):
    options = {"basic_skills": "vanilla"}

    def test_basic_skills_nowhere(self) -> None:
        for name in BASIC_SKILLS:
            self.assertNotIn(name, self.own_pool())
            self.assertNotIn(name, self.start())


class TestBasicSkillsStartWith(SkillsBase):
    options = {"basic_skills": "start_with"}

    def test_basic_skills_at_start(self) -> None:
        for name in BASIC_SKILLS:
            self.assertNotIn(name, self.own_pool())
            self.assertIn(name, self.start())


class TestBasicSkillsShuffle(SkillsBase):
    options = {"basic_skills": "shuffle"}

    def test_basic_skills_in_pool(self) -> None:
        for name in BASIC_SKILLS:
            self.assertEqual(self.own_pool().count(name), 1, name)
            self.assertNotIn(name, self.start())
