from test.bases import WorldTestBase

from ..data_loader import GAME_NAME


class LoITestBase(WorldTestBase):
    """Area Keys off: the logic tests assume the five hub areas are open (test_area_keys.py
    covers the option)."""
    game = GAME_NAME
    options = {"area_keys": False}
