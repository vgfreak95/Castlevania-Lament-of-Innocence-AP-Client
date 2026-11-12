from dataclasses import dataclass

from Options import Choice, DeathLink, PerGameCommonOptions, Toggle, Visibility


class Goal(Choice):
    """What completes your slot.
    defeat_walter: defeat Walter Bernhard at the top of the Pagoda of the Misty Moon.
    defeat_death: defeat Death, who is fought after Walter."""
    display_name = "Goal"
    option_defeat_walter = 0
    option_defeat_death = 1
    default = 0


class TorchSanity(Toggle):
    """NOT IMPLEMENTED YET: add sub-weapon torches and candles as locations. Ignored for now."""
    display_name = "Torch Sanity (not implemented)"
    visibility = Visibility.none


class EnemyDropSanity(Toggle):
    """NOT IMPLEMENTED YET: add enemy common/rare drops as locations. Ignored for now."""
    display_name = "Enemy Drop Sanity (not implemented)"
    visibility = Visibility.none


class LoIDeathLink(DeathLink):
    """NOT IMPLEMENTED YET: the client doesn't send or receive deaths. Ignored for now."""
    display_name = "Death Link (not implemented)"
    visibility = Visibility.none


@dataclass
class LoIOptions(PerGameCommonOptions):
    goal: Goal
    death_link: LoIDeathLink
    torch_sanity: TorchSanity
    enemy_drop_sanity: EnemyDropSanity
