# Castlevania: Lament of Innocence — Archipelago

Play Castlevania: Lament of Innocence (PS2) in an [Archipelago](https://archipelago.gg)
multiworld randomizer. Floor pickups and boss rewards are shuffled into a shared item pool with
other players' games, and the items you find may belong to someone else's world.

You don't need to patch the ISO. A PCSX2 patch changes the game while it runs, and the
Archipelago client talks to PCSX2 directly.

## What you need

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.4 or newer
- [PCSX2](https://pcsx2.net/) 2.x
- Your own copy of Castlevania: Lament of Innocence, **US version (SLUS-20733)**, as an ISO
- From this repository's [Releases](../../releases) page:
  - `lament_of_innocence.apworld`
  - `28270F7D.pnach`

## Setup

### 1. Install the apworld

Double-click `lament_of_innocence.apworld`, or copy it into Archipelago's `custom_worlds` folder
(by default `C:\ProgramData\Archipelago\custom_worlds`). Then restart the Archipelago Launcher.

### 2. Install the PCSX2 patch

1. Copy `28270F7D.pnach` into PCSX2's `patches` folder. On Windows this is usually
   `Documents\PCSX2\patches`. To find it, use **Tools > Open Data Directory** in PCSX2.
2. In PCSX2, right-click the game in your library, open **Properties > Patches** and turn on
   **Archipelago Pickups**.
3. Optional: turn on **Archipelago Menu and Minimap** for a small map of the rooms you've visited
   in the top-right corner. Rooms that still have unchecked Archipelago pickups get an orange
   marker. Tap **L3** to show or hide it; hold **L3** for about 3 seconds to open the Archipelago
   Menu's **Minimap Options** (zoom, size, corner, opacity, room shapes and which markers to
   show). Minimap settings last until you reset the console. This patch also adds the **Savewarp
   Ticket** to Rinaldo's shop (2000 gold, one per game): use it in a save room to warp to any save
   room you've been in. It's never used up.

### 3. Turn on PINE in PCSX2

The client connects to PCSX2 through PINE. Go to **Settings > Advanced**, enable **PINE** and leave
the slot at **28011**.

### 4. Create your player YAML

In the Archipelago Launcher, use **Generate Template Options** or **Options Creator** (0.6.7 or above)

## Options


| Option       | Values                                 | Description                                        |
|--------------|----------------------------------------|----------------------------------------------------|
| `goal`       | `defeat_walter` (default), `defeat_death` | Beat Walter Bernhard, or Death (fought after Walter). |

## Playing

1. Start PCSX2 and boot the game. The Archipelago Pickups patch must be on.
2. In the Archipelago Launcher, open **Lament of Innocence Client**.
3. Connect to the server: `/connect address:port`.
4. Start a **new game**.

When you pick up a location's item or beat a boss, the check is sent. A message box shows what
you found and who it belongs to. Items other players send you arrive in game with a message box.

Extra commands in the client:

| Command       | What it does                                                        |
|---------------|---------------------------------------------------------------------|
| `/pcsx2`      | Shows whether the client is connected to PCSX2 and the game.        |
| `/popups`     | Turns the in-game "sent item" popups on or off.                     |
| `/slot 28011` | Changes the PINE slot, if you set PCSX2 to use a different one.     |
| `/map`        | Opens the 3D map tracker in your browser (see below).               |

### Map tracker

The client's **Map** tab shows a top-down map of the castle. It shows the rooms you've visited,
where Leon is and which way he faces, and the doors you've been through. Rooms whose Archipelago
pickups are all checked turn green. Rooms with pickups left get an orange marker, and so do
unchecked torches with Torch Sanity on. Click a room to list its locations. Drag to pan, scroll to
zoom, double-click (or **Fit**) to see the whole area. **Follow** keeps Leon centred and switches
areas with him. By default Leon's floor is drawn on top and the other floors are dimmed; the floor
menu can show all floors or just one.

`/map` opens the same map in 3D in your browser instead. Drag to orbit, right-drag to pan, scroll
to zoom; **F** toggles following Leon, **T** is a top view. The page needs internet access the
first time: its 3D library (three.js) loads from a CDN.

The map uses the client's own connection to PCSX2, so it runs alongside the game with nothing
else to set up. Each area's map is read from your game the first time Leon is in it while the
client is connected, and is kept on your PC, so nothing from the game ships with the apworld.

## What's randomized

- **Locations:** 112 unique floor pickups, from the Prelude to the Prison of Eternal Torture,
  plus the rewards of 9 bosses: the five area bosses, the three Elementals and the Forgotten One.
  With **Torch Sanity** on, every breakable torch is a location too: an unchecked torch burns
  red, and breaking it checks the location (it drops nothing).
- **Items:** whips (except the starting Whip of Alchemy), the five keys, tablets, Dragon Crest,
  Unlock Jewel, Curtain Time Bell, all seven orbs, armour, accessories and relics (including
  shop items), HP/Heart/MP Max Ups and filler (potions, hearts, money, food).

Every vanilla gate is still in place: the key doors, the e Tablet door, the Curtain Time Bell, the
Unlock Jewel door, the Pagoda seal and the way up to Walter. To reach Walter you need the five
coloured orbs (Red, Blue, Yellow, Green, Purple), the five area bosses defeated, the Dragon Crest
and the Vampire Killer.

## Troubleshooting

- **The client can't connect to PCSX2.** Check that PINE is enabled with slot 28011 and that the
  game is running. Type `/pcsx2` in the client to see the connection state.
- **Pickups give their normal items and no checks are sent.** The patch isn't active. Make sure
  `28270F7D.pnach` is in the `patches` folder and **Archipelago Pickups** is turned on in the
  game's Patches settings.
- **The game isn't recognised.** Only the US version (SLUS-20733) is supported.

## Building from source

This is only needed if you're working on the project. Build the PCSX2 patch with
`.\build.ps1`, which needs Docker and the `ps2dev/ps2dev` image (settings are in `config.toml`).
Package the apworld with `py -3.13 tools\build_apworld.py`, and run the client tests with
`py -3.13 tools\test_ap_client.py`. Both outputs go to `build\`.

## AI Disclaimer: AI was used in helping with the creation of this Archipelago

AI Tools Used: Claude Code with Model: Opus 5.5
The purpose of the tools was to help reverse engineer the game and perform essentially a basic decompilation, for the aspects needed to create the archipelago.
The tools were used extensively. I generally helped guide Claude to the answers and helped with testing and ensuring its accuracy
I have reviewed most of the code and understand the debug menu, archipelago item pickups, and I designed the menu architecture.

For logic, the already existing randomizer of the game by Casj was used with his permission from the start.
