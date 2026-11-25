# Castlevania - Lament of Innocence

## What does randomization do to this game?

Every unique floor pickup (112 of them, from the Prelude to the Prison of Eternal Torture) and the
reward of nine bosses (the five area bosses, the three Elementals and the Forgotten One) become
Archipelago locations. Picking one up, or beating the boss, sends a check; the item you receive
comes from the multiworld.
With [Shop Sanity](#shop-sanity), Rinaldo's shop sells locations too.

The game runs on an unmodified ISO with runtime patches, so every vanilla gate is still there:
the key doors, the e Tablet door, the Curtain Time Bell, the Unlock Jewel door, the Pagoda seal and
the way up to Walter.

## What items are shuffled?

- All whips (except the starting Whip of Alchemy), the five keys, the tablets, Dragon Crest, Unlock
  Jewel, Curtain Time Bell and all seven orbs.
- Armour, accessories and relics, including ones normally sold in Rinaldo's shop.
- The HP, Heart and MP Max Ups found in the world.
- Filler: potions, hearts, money, food.
- With `area_keys` (on by default): five new area keys, see [Area Keys](#area-keys).
- The whip skills, see [Whip Skills](#whip-skills).
- With `progressive_brooch`: two Progressive Brooches instead of Heart Brooch and Mobius's Brooch.
  The first one you receive is the Heart Brooch, the second Mobius's Brooch.
- With `progressive_plates`: four Progressive Plates instead of the four plates, received in order:
  Earth Plate, Meteor Plate, Moonlight Plate, Solar Plate.

The new [Savewarp Ticket](#savewarp-ticket) isn't shuffled: it's only sold in Rinaldo's shop.

Rinaldo no longer sells the items of his that are in the pool: the four plates, Mobius's Brooch and
the Jade Mask only come from the multiworld. You can still sell them to him.

The Svarog Statue is shuffled like any other relic, and you don't start with it. The Prelude's
tutorial Golden Knight, which normally only takes damage from the Svarog Statue's flames, can be
beaten with the whip or a sub-weapon. Getting the Svarog Statue no longer equips it, so the relic
you have equipped stays.

## Shop Sanity

With `shop_sanity` on (the default is off), Rinaldo's shop sells Archipelago locations. Each one
holds any item, from this world or another (progression included), and can be bought once.

- Rinaldo's stock has 35 rows. Each of his 15 vanilla shop items has its own option, on by
  default, that keeps it on sale at its vanilla price: `shop_potion`, `shop_high_potion`,
  `shop_serum`, `shop_uncurse_potion`, `shop_magical_ticket`, `shop_memorial_ticket`,
  `shop_diamond`, `shop_ruby`, `shop_sapphire`, `shop_opal`, `shop_turquoise`, `shop_zircon`,
  `shop_music_box`, `shop_sacrificial_doll`, `shop_white_bishop`. Every row not kept is a
  location: 20 locations with all 15 items kept, up to 35 with none.
- The locations are named `Rinaldo's Shop: Item 1`, `Item 2` and so on (location group `Shop`).
  The Buy list shows 20 of them at a time, in that order; the next ones appear as you buy earlier
  ones.
- `shop_prices` sets what the locations cost:
  - `custom`: a random price from 10 gold up to `shop_custom_price` each (2-10000, default 1000;
    below 10, every location costs exactly that).
  - `affordable`: a random price from 10 to 500 gold each.
  - `normal` (the default): a random price from 500 to 2000 gold each.
  - `unaffordable`: a random price from 1000 to 5000 gold each.

  Every price is a multiple of 10 gold (2178 becomes 2180). The spoiler log lists every
  location's price.
- Gold isn't part of the logic: a shop location only needs the shop, which is open from the
  start. You may have to farm gold before you can buy what you need.
- Each row shows what it holds and for whom. A bought location stays sold out: the client tells
  the game which ones are checked every time it connects, so they stay off the list after a
  reload or a console reset too.
- The shop locations add the same number of filler items (or traps, with `trap_chance`) to the
  item pool.

## Area Keys

With `area_keys` on (the default), each of the five areas you reach from the floating rocks in the
Prelude's hub needs its own key. These keys are new items that don't exist in the vanilla game:

| Key | Opens | Looks like |
|-----|-------|------------|
| Sacred Remains Key | House of Sacred Remains | Yellow Dragon Key |
| Mystery Lab Key | Anti-Soul Mystery Lab | Red Phoenix Key |
| Waterfall Palace Key | Dark Palace of Waterfalls | Black Turtle Key |
| Forgotten Garden Key | Garden Forgotten by Time | Blue Dragon Key |
| Ghostly Theatre Key | Ghostly Theatre | White Tiger Key |

Each key looks like the vanilla key that area's own key door needs. They go in your key items, like
any other key, and are kept in your save.

**Options**

- `starting_area`: the area whose key you start with: `house_of_sacred_remains`,
  `anti_soul_mystery_lab`, `dark_palace_of_waterfalls`, `garden_forgotten_by_time` or
  `ghostly_theatre`. The default, `random`, picks one of the five.
- `starting_area_keys` (0-5, default 1): how many area keys you start with. The `starting_area` key
  is always one of them; the others are picked at random. With 5 you start with every key. With 0
  you start with none (`starting_area` isn't used): your first key comes from the checks open from
  the start, in the Prelude's hub and the Prison of Eternal Torture (and their torches with Torch
  Sanity), or from another world.
- The keys you don't start with are shuffled into the item pool. They take the place of filler,
  not of any vanilla item.

**In game**

- Stand on an area's rock without its key and the rock stays put. A message says which area is
  sealed and which key it needs. Walk off and come back once you have the key.
- The hub itself, the Prison of Eternal Torture and the Boss Rush rock in the middle of the hub
  aren't affected. The Pagoda of the Misty Moon still needs its vanilla seal (the five orbs and
  the five area bosses), so in practice it needs every area key.
- In the vanilla game, picking up the hub's Map walks Leon onto the House of Sacred Remains rock
  for his first trip. While that area is sealed, this is skipped and you keep control. If the
  House of Sacred Remains is your starting area, it happens as usual.
- The client tells the game which areas are locked every time it connects. After a console reset
  the areas stay open until the client is connected again.

With `area_keys` off, the five areas are open from the start, as in the vanilla game, and the area
keys don't exist.

## Whip Skills

Leon's whip techniques are items. Defeating enemies, guarding and Quick Stepping no longer teach
them: a skill is learned when its item arrives, with a "Received" message. Its move then works
straight away.

- In the item pool: Extension, Draw Up, Vertical High, Rising Shot, Fast Rising, Spinning Blast,
  Energy Blast, Sonic Edge, A Extension 1, A Extension 2, Step Attack, Falcon Claw and Quick
  Step 2.
- Quick Step and Perfect Guard, which the game normally teaches almost at once, follow the
  `basic_skills` option:
  - `vanilla` (the default): learned the normal way (Quick Step after 3 kills, Perfect Guard after
    guarding 15 attacks). They aren't in the item pool.
  - `start_with`: learned from the start.
  - `shuffle`: in the item pool like the other skills.
- No location needs a skill yet: they are useful items, not progression.
- The client tells the game which skills it may still teach every time it connects. Until it is
  connected after a console reset, no skill is learned the normal way (kills still count, so a
  vanilla skill whose conditions are already met is learned as soon as the client connects).
- Only the main game mode (Leon) is covered.

## Quality of life

- `wolfs_foot_qol`: how fast Wolf's Foot drains MP, as a percentage of the normal 10 MP a second:
  `0` uses no MP at all, `50` drains half as fast (it lasts twice as long), `100` (the default) is
  normal. The client turns it on every time it connects; after a console reset it
  drains at the normal rate until the client is connected again.

## Traps

With `trap_chance` above 0 (the default is 0), that percent of the filler items become traps. Each
trap's weight option (`paralysis_trap_weight`, `curse_trap_weight`, `stone_trap_weight`,
`knockback_trap_weight`, `poison_trap_weight`, 0-10, default 1) sets how likely a trap is to be
that one; a weight of 0 leaves it out.

- **Paralysis Trap**: Leon is paralyzed, as if a paralyzing attack hit him.
- **Curse Trap**: Leon is cursed, losing his whip skills until it wears off.
- **Stone Trap**: Leon is turned to stone until you mash free.
- **Poison Trap**: Leon is poisoned, losing 1 HP every few seconds (never below 1) until it wears
  off.
- These four come with a light hit that does no damage, the way the enemy attacks that cause
  them do. They wait while Leon is turned to stone.
- **Knockback Trap**: Leon is smacked backwards across the room, like the strongest enemy hits,
  without taking damage. It waits while Leon is dead or turned to stone.

The status effects last as long as the vanilla ones and are cured the vanilla ways (Uncurse
Potion, Diamond and so on). A trap only takes effect once; reloading an older save doesn't repeat it
unless that save is from before the trap arrived.

## What is the goal?

- `defeat_walter` (default): beat Walter Bernhard.
- `defeat_death`: beat Death, after Walter.

Reaching Walter needs the five coloured orbs (Red, Blue, Yellow, Green, Purple), the five area
bosses defeated, the Dragon Crest and the Vampire Killer.

## What does another world's item look like in this game?

The pickup still looks like its vanilla item. Picking it up shows a message box with what was sent
and to whom.

## Archipelago Menu and Minimap

The **Archipelago** patch draws a small map
in a corner of the screen. It shows the rooms you've visited on Leon's current floor, with an arrow
for Leon pointing the way he faces.

- Room shapes come from the game's own pause map, so rooms look the way they do there.
- Save rooms are red. Rooms where you've collected every Archipelago pickup turn green. Rooms that
  still have unchecked pickups get an orange marker.
- Room transitions (the doorways to other rooms) appear once you've been in a room.
- Tap **L3** to show or hide it.

Hold **L3** for about 3 seconds to open the **Archipelago Menu** (long enough that it doesn't open
by accident in combat). The game pauses while it is open. Up/Down select, Cross opens a page or
confirms, Left/Right change a setting, Triangle or Circle goes back (and closes the menu from its
first page), and tapping L3 closes it.

- **Minimap Options**: the minimap settings below.

| Minimap setting | Choices |
|---------|---------|
| Zoom | how much of the floor fits on the map |
| Size | Small, Medium, Large |
| Corner | Top right, Top left, Bottom right, Bottom left |
| Opacity | how see-through the map is |
| Room shapes | On: the real room shapes. Off: plain boxes |
| Room transitions | show the doorways |
| AP pickup markers | show the orange markers |
| Cleared rooms green | colour rooms green once their pickups are all checked |

Settings last until you reset the console.

## Savewarp Ticket

The **Archipelago** patch also adds a new item, the **Savewarp Ticket**: a red
Memorial Ticket that warps you between save rooms.

- **Where to get it**: buy it from Rinaldo's shop (Items tab) for 2000 gold. It isn't in the
  Archipelago item pool, so it never turns up as a pickup or from another world. You can only buy
  one: once you have it, it leaves the shop's list. It can't be sold.
- **Using it**: use it from the quick item menu while you're standing in a save room. A list of
  every save room you've already been in opens, named the way the save file list names them (for
  example "House of Sacred Remains 1F"). Rooms that share a name get a number ("Garden Forgotten
  By Time 1F 2"), and "(here)" marks the one you're in. Up/Down select, Cross warps, Triangle or Circle
  cancels. The game pauses while the list is open.
- **The warp**: the ticket plays the Memorial Ticket's animation, then you arrive at the chosen
  room's first doorway.
- **It's never used up**: keep it and use it as often as you like.
- Outside a save room the ticket does nothing, and a message says it only works in a save room.
- The list comes from the game's own visited-room record, so it is kept in your save.

## Not implemented yet

Enemy-drop sanity is declared as an option but does nothing yet.
