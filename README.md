# Castlevania: Lament of Innocence — Archipelago Client

[Archipelago](https://archipelago.gg) multiworld support for Castlevania: Lament of Innocence
(PS2, US release SLUS-20733) on PCSX2. It works on an unmodified ISO and has two parts:

- **The apworld** (`apworld/lament_of_innocence/`): the Archipelago world (items, locations,
  logic, options) plus the game client, which talks to PCSX2 over PINE.
- **The pnach patch** (`src/`): the "Archipelago Pickups" EE patch. It turns floor pickups and
  boss rewards into location checks, receives items from the client and shows message boxes.

See `apworld/lament_of_innocence/docs/` for what gets randomized and for the player setup guide.

## Repository layout

```
apworld/lament_of_innocence/   the world and the client (client.py, pine.py, game_interface.py)
  data/                        items.json, locations.json, extra_locations.json
  docs/                        game info page and setup guide
  test/                        world logic tests (run inside an Archipelago checkout)
src/                           the pickup patch (pickup.c, msgbox.c) and game addresses (game.h)
game.ld                        linker script: game function and data addresses
config.toml                    patch build settings: load address, hooks, pnach output
build.ps1 / build.sh           build the patch (Windows wrapper / compile script)
tools/                         build, packaging, test and debugging scripts
```

## Requirements

- Python 3.13 (on Windows, use the `py` launcher: `py -3.13`)
- [Docker](https://www.docker.com/) for the `ps2dev/ps2dev` toolchain image. Or set
  `docker_image = ""` in `config.toml` and put the `mips64r5900el-ps2-elf-*` tools on your PATH.
- [Archipelago](https://github.com/ArchipelagoMW/Archipelago) 0.6.4 or newer
- PCSX2 with PINE enabled (Settings > Advanced > PINE, slot 28011)

## Building

### 1. The pnach patch

With Docker running:

```powershell
.\build.ps1             # compile -> build\28270F7D.pnach
.\build.ps1 -Install    # also copy it into PCSX2's patches folder
```

On Linux or macOS, run `python3 tools/build.py [--install]`.

The build regenerates `src/ap_locations.h` from the location data, compiles `src/pickup.c` and
`src/msgbox.c` at `0xF9000` and writes the pnach. To install it somewhere other than PCSX2's
default patches folder, set `patches_dir` in `config.toml`. In PCSX2, enable both the
"Archipelago Pickups" and "Debug printf" patches for the game.

### 2. The apworld

```powershell
py -3.13 tools\build_apworld.py                 # -> build\lament_of_innocence.apworld
py -3.13 tools\build_apworld.py --install       # also copy it to C:\ProgramData\Archipelago\custom_worlds
py -3.13 tools\build_apworld.py --dev C:\path\to\Archipelago   # also mirror it into a source checkout
```

The `.apworld` doesn't include the world's `test/` folder.

## Testing

Client protocol tests run against a fake PCSX2 in memory, so they need neither an emulator nor
Archipelago:

```powershell
py -3.13 tools\test_ap_client.py -v
```

The world logic tests in `apworld/lament_of_innocence/test/` need an Archipelago source checkout.
Mirror the world into it with `build_apworld.py --dev <checkout>`, then run pytest there on
`worlds/lament_of_innocence`.

## Debugging tools

Each of these connects to a running PCSX2 over PINE:

- `py -3.13 tools\pickup_client.py`: prints pickup and location-check events from the patch.
- `py -3.13 tools\send_item.py <item id hex> [sender]`: sends one item to the game as a fake
  server would, e.g. `send_item.py 2A Player2`.

`tools\loc_scan.py` fills the `game_key` values in `locations.json` from an in-game location scan.
That scan is part of the separate debug-menu patch, which this repository doesn't include.

## Playing

1. Boot the vanilla ISO in PCSX2 with the patch enabled.
2. Open the Lament of Innocence Client from the Archipelago Launcher.
3. Connect with `/connect address:port` and start a new game.
