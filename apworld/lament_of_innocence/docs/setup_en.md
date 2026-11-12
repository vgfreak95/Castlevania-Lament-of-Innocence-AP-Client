# Castlevania - Lament of Innocence Setup Guide

## Required software

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.4 or newer.
- [PCSX2](https://pcsx2.net/) 2.x with PINE enabled (Settings > Advanced > PINE, slot 28011).
- A US copy of Castlevania: Lament of Innocence (SLUS-20733), as an ISO.
- The Archipelago pnach patch for the game (`28270F7D.pnach`), installed in PCSX2's `patches`
  folder, with the **Archipelago Pickups** patch turned on in the game's Properties > Patches.

## Installation

1. Put `lament_of_innocence.apworld` in Archipelago's `custom_worlds` folder.
2. Generate a template YAML from the Archipelago Launcher (Generate Template Options), or write one:

```yaml
name: Leon
game: Castlevania - Lament of Innocence
Castlevania - Lament of Innocence:
  goal: defeat_walter
```

## Playing

1. Start PCSX2 with the pnach enabled and boot the game (vanilla ISO, no randomizer patch).
2. Open the Lament of Innocence Client from the Archipelago Launcher.
3. Connect to the server (`/connect address:port`). The client talks to PCSX2 over PINE.
4. Start a new game. Items you receive appear with a message box.
