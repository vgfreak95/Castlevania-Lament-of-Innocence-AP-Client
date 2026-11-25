from dataclasses import dataclass

from Options import (Choice, DeathLink, DefaultOnToggle, OptionGroup, PerGameCommonOptions, Range,
                     Toggle, Visibility)


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
    five. Not used when Starting Area Keys is 0."""
    display_name = "Starting Area"
    option_house_of_sacred_remains = 0
    option_anti_soul_mystery_lab = 1
    option_dark_palace_of_waterfalls = 2
    option_garden_forgotten_by_time = 3
    option_ghostly_theatre = 4
    default = "random"


class StartingAreaKeys(Range):
    """With Area Keys: how many area keys you start with. The Starting Area's key is always one
    of them; the others are picked at random. 0: you start with no key at all, and the first one
    has to come from the checks open from the start (the Prelude's hub and the Prison of Eternal
    Torture, plus their torches with Torch Sanity) or from another world."""
    display_name = "Starting Area Keys"
    range_start = 0
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


class WolfsFootQoL(Range):
    """How fast Wolf's Foot drains MP, in percent of the normal rate (10 MP a second): 0 = it
    uses no MP at all, 50 = half (it lasts twice as long), 100 = normal."""
    display_name = "Wolf's Foot QoL"
    range_start = 0
    range_end = 100
    default = 100


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


class ShopSanity(Toggle):
    """Rinaldo's shop sells Archipelago locations. His shop has 35 rows: the vanilla items kept
    on sale by the "Shop Sells" options below take theirs, and every other row is a location
    (20 to 35 of them) that holds any item, from this world or another, and can be bought once.
    The Buy list shows 20 of them at a time; the next ones appear as you buy them. A bought
    location stays sold out. Gold isn't part of the logic: every location only needs the shop."""
    display_name = "Shop Sanity"


class ShopPrices(Choice):
    """With Shop Sanity: what the location rows cost (the kept vanilla items keep their vanilla
    prices).
    custom: a random price from 10 gold up to Shop Custom Price each.
    affordable: a random price from 10 to 500 gold each.
    normal: a random price from 500 to 2000 gold each.
    unaffordable: a random price from 1000 to 5000 gold each.
    Prices are multiples of 10 gold."""
    display_name = "Shop Prices"
    option_custom = 0
    option_affordable = 1
    option_normal = 2
    option_unaffordable = 3
    default = 2


class ShopCustomPrice(Range):
    """With Shop Sanity and Shop Prices custom: the most a location row can cost, in gold. Each
    row gets a random price, a multiple of 10, from 10 up to this; below 10, every row costs
    exactly this (2 is the least the shop charges)."""
    display_name = "Shop Custom Price"
    range_start = 2
    range_end = 10000
    default = 1000


class ShopPotion(DefaultOnToggle):
    """With Shop Sanity: the Potion stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Potion"


class ShopHighPotion(DefaultOnToggle):
    """With Shop Sanity: the High Potion stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells High Potion"


class ShopSerum(DefaultOnToggle):
    """With Shop Sanity: the Serum stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Serum"


class ShopUncursePotion(DefaultOnToggle):
    """With Shop Sanity: the Uncurse Potion stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Uncurse Potion"


class ShopMagicalTicket(DefaultOnToggle):
    """With Shop Sanity: the Magical Ticket stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Magical Ticket"


class ShopMemorialTicket(DefaultOnToggle):
    """With Shop Sanity: the Memorial Ticket stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Memorial Ticket"


class ShopDiamond(DefaultOnToggle):
    """With Shop Sanity: the Diamond stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Diamond"


class ShopRuby(DefaultOnToggle):
    """With Shop Sanity: the Ruby stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Ruby"


class ShopSapphire(DefaultOnToggle):
    """With Shop Sanity: the Sapphire stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Sapphire"


class ShopOpal(DefaultOnToggle):
    """With Shop Sanity: the Opal stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Opal"


class ShopTurquoise(DefaultOnToggle):
    """With Shop Sanity: the Turquoise stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Turquoise"


class ShopZircon(DefaultOnToggle):
    """With Shop Sanity: the Zircon stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Zircon"


class ShopMusicBox(DefaultOnToggle):
    """With Shop Sanity: the Music Box stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Music Box"


class ShopSacrificialDoll(DefaultOnToggle):
    """With Shop Sanity: the Sacrificial Doll stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells Sacrificial Doll"


class ShopWhiteBishop(DefaultOnToggle):
    """With Shop Sanity: the White Bishop stays on sale in Rinaldo's shop, as in the vanilla game. Off:
    its row becomes one more Archipelago location."""
    display_name = "Shop Sells White Bishop"


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
    shop_sanity: ShopSanity
    shop_prices: ShopPrices
    shop_custom_price: ShopCustomPrice
    shop_potion: ShopPotion
    shop_high_potion: ShopHighPotion
    shop_serum: ShopSerum
    shop_uncurse_potion: ShopUncursePotion
    shop_magical_ticket: ShopMagicalTicket
    shop_memorial_ticket: ShopMemorialTicket
    shop_diamond: ShopDiamond
    shop_ruby: ShopRuby
    shop_sapphire: ShopSapphire
    shop_opal: ShopOpal
    shop_turquoise: ShopTurquoise
    shop_zircon: ShopZircon
    shop_music_box: ShopMusicBox
    shop_sacrificial_doll: ShopSacrificialDoll
    shop_white_bishop: ShopWhiteBishop
    enemy_drop_sanity: EnemyDropSanity


# Sections (drop-downs) on the WebHost options pages and in generated YAMLs. Options not listed
# here (Death Link) stay in the default "Game Options" section.
option_groups = [
    OptionGroup("Starting and Goal", [
        Goal,
        StartingArea,
        StartingAreaKeys,
        BasicSkills,
    ]),
    OptionGroup("Shuffles", [
        AreaKeys,
        TorchSanity,
        EnemyDropSanity,
    ]),
    OptionGroup("Quality of Life", [
        ProgressiveBrooch,
        ProgressivePlates,
        WolfsFootQoL,
    ]),
    OptionGroup("Shop Sanity", [
        ShopSanity,
        ShopPrices,
        ShopCustomPrice,
        ShopPotion,
        ShopHighPotion,
        ShopSerum,
        ShopUncursePotion,
        ShopMagicalTicket,
        ShopMemorialTicket,
        ShopDiamond,
        ShopRuby,
        ShopSapphire,
        ShopOpal,
        ShopTurquoise,
        ShopZircon,
        ShopMusicBox,
        ShopSacrificialDoll,
        ShopWhiteBishop,
    ]),
    OptionGroup("Traps", [
        TrapChance,
        ParalysisTrapWeight,
        CurseTrapWeight,
        StoneTrapWeight,
        KnockbackTrapWeight,
        PoisonTrapWeight,
    ]),
]
