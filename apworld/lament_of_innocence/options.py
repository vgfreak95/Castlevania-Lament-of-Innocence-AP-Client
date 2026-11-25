from dataclasses import dataclass

from Options import (Choice, DeathLink, DefaultOnToggle, PerGameCommonOptions, Range, Toggle,
                     Visibility)


class Goal(Choice):
    """What completes your slot.
    defeat_walter: defeat Walter Bernhard at the top of the Pagoda of the Misty Moon.
    defeat_death: defeat Death, who is fought after Walter."""
    display_name = "Goal"
    option_defeat_walter = 0
    option_defeat_death = 1
    default = 0


class AreaKeys(DefaultOnToggle):
    """Each of the five areas reached from the floating rocks in the Prelude's hub needs its own
    key: Sacred Remains Key (House of Sacred Remains), Mystery Lab Key (Anti-Soul Mystery Lab),
    Waterfall Palace Key (Dark Palace of Waterfalls), Forgotten Garden Key (Garden Forgotten by
    Time) and Ghostly Theatre Key (Ghostly Theatre). Without the key, the area's rock won't lift.
    You start with the keys picked by Starting Area and Starting Area Keys; the rest are in the
    item pool."""
    display_name = "Area Keys"


class StartingArea(Choice):
    """With Area Keys: the area whose key you start with. random (the default) picks one of the
    five."""
    display_name = "Starting Area"
    option_house_of_sacred_remains = 0
    option_anti_soul_mystery_lab = 1
    option_dark_palace_of_waterfalls = 2
    option_garden_forgotten_by_time = 3
    option_ghostly_theatre = 4
    default = "random"


class StartingAreaKeys(Range):
    """With Area Keys: how many area keys you start with. The Starting Area's key is always one
    of them; the others are picked at random."""
    display_name = "Starting Area Keys"
    range_start = 1
    range_end = 5
    default = 1


class BasicSkills(Choice):
    """Quick Step and Perfect Guard, the two whip skills Leon normally learns almost at once (Quick
    Step after 3 kills, Perfect Guard after guarding 15 attacks). The other 13 skills are always
    in the item pool and are never learned from kills.
    vanilla: learned the normal way, not in the item pool.
    start_with: learned from the start.
    shuffle: in the item pool like the other skills."""
    display_name = "Basic Skills"
    option_vanilla = 0
    option_start_with = 1
    option_shuffle = 2
    default = 0


class ProgressiveBrooch(Toggle):
    """Replaces Heart Brooch and Mobius's Brooch with two Progressive Brooches: the first one you
    receive is the Heart Brooch, the second Mobius's Brooch."""
    display_name = "Progressive Brooch"


class ProgressivePlates(Toggle):
    """Replaces the four plates with four Progressive Plates, received in order: Earth Plate,
    Meteor Plate, Moonlight Plate, Solar Plate."""
    display_name = "Progressive Plates"


class WolfsFootQoL(Toggle):
    """Wolf's Foot drains MP at half the normal rate (5 MP a second instead of 10), so it lasts
    twice as long."""
    display_name = "Wolf's Foot QoL"


class TrapChance(Range):
    """Percent chance for each filler item to be replaced with a trap instead (the trap is picked
    with the trap weights below)."""
    display_name = "Trap Chance"
    range_start = 0
    range_end = 100
    default = 0


class ParalysisTrapWeight(Range):
    """How likely a trap is to be a Paralysis Trap: Leon is paralyzed, as if hit by a paralyzing
    attack."""
    display_name = "Paralysis Trap Weight"
    range_start = 0
    range_end = 10
    default = 1


class CurseTrapWeight(Range):
    """How likely a trap is to be a Curse Trap: Leon is cursed, losing his whip skills until it
    wears off."""
    display_name = "Curse Trap Weight"
    range_start = 0
    range_end = 10
    default = 1


class StoneTrapWeight(Range):
    """How likely a trap is to be a Stone Trap: Leon is turned to stone until he mashes free."""
    display_name = "Stone Trap Weight"
    range_start = 0
    range_end = 10
    default = 1


class KnockbackTrapWeight(Range):
    """How likely a trap is to be a Knockback Trap: Leon is smacked backwards across the room,
    without taking damage."""
    display_name = "Knockback Trap Weight"
    range_start = 0
    range_end = 10
    default = 1


class PoisonTrapWeight(Range):
    """How likely a trap is to be a Poison Trap: Leon is poisoned, slowly losing HP (never below
    1) until it wears off."""
    display_name = "Poison Trap Weight"
    range_start = 0
    range_end = 10
    default = 1


class TorchSanity(Choice):
    """Every breakable torch (1324 of them) becomes a location. A torch that is still unchecked
    burns with a red flame; breaking it checks the location and drops nothing. Once it's checked
    it burns normally and drops hearts again. Sub-weapon torches keep their sub-weapon.
    off: torches are not locations.
    filler_only: torches are locations, but only ever hold filler items and traps.
    full: torches can hold anything, progression included. Torches are only gated by their
    area's access and by the known locks of the room they're in."""
    display_name = "Torch Sanity"
    option_off = 0
    option_filler_only = 1
    option_full = 2
    default = 0


class EnemyDropSanity(Toggle):
    """NOT IMPLEMENTED YET: add enemy common/rare drops as locations. Ignored for now."""
    display_name = "Enemy Drop Sanity (not implemented)"
    visibility = Visibility.none


class LoIDeathLink(DeathLink):
    """When Leon dies, everyone else with Death Link dies too, and the other way round.
    A death you receive kills Leon as soon as normal gameplay allows (not during menus or
    message boxes). The client's /deathlink command turns it on or off for a session."""
    display_name = "Death Link"


@dataclass
class LoIOptions(PerGameCommonOptions):
    goal: Goal
    death_link: LoIDeathLink
    area_keys: AreaKeys
    starting_area: StartingArea
    starting_area_keys: StartingAreaKeys
    basic_skills: BasicSkills
    progressive_brooch: ProgressiveBrooch
    progressive_plates: ProgressivePlates
    wolfs_foot_qol: WolfsFootQoL
    trap_chance: TrapChance
    paralysis_trap_weight: ParalysisTrapWeight
    curse_trap_weight: CurseTrapWeight
    stone_trap_weight: StoneTrapWeight
    knockback_trap_weight: KnockbackTrapWeight
    poison_trap_weight: PoisonTrapWeight
    torch_sanity: TorchSanity
    enemy_drop_sanity: EnemyDropSanity
