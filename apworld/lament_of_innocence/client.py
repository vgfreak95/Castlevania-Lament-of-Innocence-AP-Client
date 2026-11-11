"""Archipelago client for Castlevania: Lament of Innocence on PCSX2.

Needs the "Archipelago Pickups" pnach (src/pickup.c) on the vanilla SLUS-20733 ISO and PINE
enabled in PCSX2 (Settings > Advanced > PINE, slot 28011). The RAM protocol is in
game_interface.py.

Start it from the Archipelago Launcher ("Lament of Innocence Client"), or for development:
    py -3.13 Launcher.py "Lament of Innocence Client"
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional, Set, Tuple

import Utils
from CommonClient import (ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled,
                          logger, server_loop)
from NetUtils import ClientStatus, NetworkItem

from .data_loader import BASE_ID, GAME_NAME, ITEMS, LOCATIONS
from .game_interface import (EV_LOCATION, GOAL_DEATH, GOAL_WALTER, GameMismatch, LoIInterface,
                             build_key_map)
from .pine import DEFAULT_SLOT, Pine, PineError

POLL_INTERVAL = 0.1           # seconds between game polls (the event ring holds 8 events)
RECONNECT_INTERVAL = 2.0
GOAL_OPTION_WALTER, GOAL_OPTION_DEATH = 0, 1


class LoICommandProcessor(ClientCommandProcessor):
    ctx: "LoIContext"

    def _cmd_pcsx2(self) -> bool:
        """Show the PCSX2 / game connection state."""
        self.output(f"PCSX2: {self.ctx.game_state}")
        return True

    def _cmd_popups(self) -> bool:
        """Toggle the in-game "Sent X to Y" popups."""
        self.ctx.popups = not self.ctx.popups
        self.output(f"Sent-item popups {'on' if self.ctx.popups else 'off'}")
        return True

    def _cmd_slot(self, slot: str = "") -> bool:
        """Set the PINE slot (port) PCSX2 listens on, default 28011."""
        try:
            self.ctx.pine_slot = int(slot)
        except ValueError:
            self.output(f"PINE slot is {self.ctx.pine_slot}; usage: /slot 28011")
            return False
        self.ctx.reconnect_game = True
        self.output(f"Using PINE slot {self.ctx.pine_slot}")
        return True


class LoIContext(CommonContext):
    command_processor = LoICommandProcessor
    game = GAME_NAME
    items_handling = 0b111        # every item comes from the server, own ones too
    want_slot_data = True

    def __init__(self, server_address: Optional[str], password: Optional[str]):
        super().__init__(server_address, password)
        self.pine_slot = DEFAULT_SLOT
        self.reconnect_game = False
        self.popups = True
        self.game_state = "not connected"
        self.slot_data: Dict = {}
        self.key_to_location: Dict[int, int] = build_key_map(LOCATIONS)
        self.location_to_key: Dict[int, int] = {v: k for k, v in self.key_to_location.items()}
        self.ap_to_game_item: Dict[int, int] = {rec["ap_id"]: rec["game_id"] for rec in ITEMS}
        self.unknown_keys: Set[int] = set()
        self.goal_sent = False
        self.pending_popups: List[str] = []
        unmapped = sum(1 for rec in LOCATIONS if rec.get("game_key") is None)
        if unmapped:
            logger.warning(f"{unmapped} locations have no game_key yet (run tools/loc_scan.py); "
                           "picking them up won't send a check.")

    def make_gui(self):
        ui = super().make_gui()
        ui.base_title = "Archipelago Lament of Innocence Client"
        return ui

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            self.slot_data = args.get("slot_data") or {}
            self.goal_sent = False
        elif cmd == "PrintJSON" and self.popups:
            self._queue_sent_popup(args)

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.slot_data = {}
        await super().disconnect(allow_autoreconnect)

    # ---- helpers ----
    def game_items(self) -> List[Tuple[int, str]]:
        """Every received item as (game item ID, sender name), in server order."""
        out = []
        for net_item in self.items_received:
            game_id = self.ap_to_game_item.get(net_item.item)
            if game_id is None:
                game_id = net_item.item - BASE_ID   # data says item ap_id = BASE + game id
            out.append((game_id, self.player_names.get(net_item.player, "Archipelago")))
        return out

    def _queue_sent_popup(self, args: dict) -> None:
        """Popup for an item we found for someone else ("Sent X to Y")."""
        if args.get("type") != "ItemSend" or self.slot is None:
            return
        item = args.get("item")
        receiver = args.get("receiving")
        if item is None or receiver is None:
            return
        if isinstance(item, (list, tuple)) and not isinstance(item, NetworkItem):
            item = NetworkItem(*item)
        if item.player != self.slot or receiver == self.slot:
            return
        receiver_name = self.player_names.get(receiver, f"Player {receiver}")
        item_name = self.item_names.lookup_in_slot(item.item, receiver)
        self.pending_popups.append(f"^C80ff8080Sent^c\n{item_name}\nto {receiver_name}")

    def goal_reached(self, goal_bits: int) -> bool:
        option = self.slot_data.get("goal", GOAL_OPTION_WALTER)
        if option == GOAL_OPTION_DEATH:
            return bool(goal_bits & GOAL_DEATH)
        return bool(goal_bits & (GOAL_WALTER | GOAL_DEATH))


async def game_tick(ctx: LoIContext, game: LoIInterface) -> None:
    """One poll: events -> checks, server items -> ring, goal, popups."""
    await asyncio.to_thread(game.heartbeat)
    events = await asyncio.to_thread(game.poll_events)
    if game.missed:
        logger.warning(f"{game.missed} game events were overwritten before the client could "
                       "read them; a location picked up meanwhile may not have been sent")
        game.missed = 0
    new_locations: Set[int] = set()
    for ev in events:
        if ev.kind != EV_LOCATION:
            continue
        ap_id = ctx.key_to_location.get(ev.location)
        if ap_id is None:
            if ev.location not in ctx.unknown_keys:
                ctx.unknown_keys.add(ev.location)
                logger.warning(f"Picked up location with game_key {ev.location} (vanilla item "
                               f"{ev.item:02X} {ev.name}), which isn't in locations.json")
            continue
        new_locations.add(ap_id)
    if new_locations:
        ctx.locations_checked |= new_locations   # CommonClient resends these on (re)connect
        if ctx.server and ctx.slot is not None:
            await ctx.check_locations(new_locations)

    if ctx.slot is not None:
        await asyncio.to_thread(game.sync_items, ctx.game_items())
        status = await asyncio.to_thread(game.status)
        if not ctx.goal_sent and ctx.goal_reached(status.goal) and ctx.server:
            ctx.finished_game = True
            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            ctx.goal_sent = True
            logger.info("Goal complete!")

    while ctx.pending_popups:
        if not await asyncio.to_thread(game.post_message, ctx.pending_popups[0]):
            break                      # queue full; try again next poll
        ctx.pending_popups.pop(0)


async def game_loop(ctx: LoIContext) -> None:
    pine: Optional[Pine] = None
    game: Optional[LoIInterface] = None
    while not ctx.exit_event.is_set():
        try:
            if game is None or ctx.reconnect_game:
                ctx.reconnect_game = False
                if pine:
                    pine.close()
                pine = Pine(ctx.pine_slot)
                await asyncio.to_thread(pine.connect)
                game = LoIInterface(pine)
                await asyncio.to_thread(game.check_game)
                ctx.game_state = f"connected on PINE slot {ctx.pine_slot}"
                logger.info(f"Connected to Lament of Innocence in PCSX2 (PINE slot {ctx.pine_slot}).")
            await game_tick(ctx, game)
            await asyncio.sleep(POLL_INTERVAL)
        except GameMismatch as exc:
            if ctx.game_state != str(exc):
                logger.warning(str(exc))
            ctx.game_state = str(exc)
            game = None
            await asyncio.sleep(RECONNECT_INTERVAL)
        except (PineError, OSError) as exc:
            if game is not None or ctx.game_state.startswith("connected"):
                logger.info(f"Lost PCSX2: {exc}. Retrying...")
            ctx.game_state = "not connected (start PCSX2 with PINE enabled)"
            game = None
            await asyncio.sleep(RECONNECT_INTERVAL)
    if pine:
        pine.close()


def launch_client(*args) -> None:
    """Entry point. The Launcher component passes the arguments as one tuple."""
    if len(args) == 1 and isinstance(args[0], (tuple, list)):
        args = tuple(args[0])
    Utils.init_logging("LamentOfInnocenceClient")

    async def main() -> None:
        parser = get_base_parser(description="Lament of Innocence Archipelago client")
        parser.add_argument("--pine-slot", type=int, default=DEFAULT_SLOT,
                            help="PCSX2 PINE slot (port), default 28011")
        parsed, _ = parser.parse_known_args(args)
        ctx = LoIContext(parsed.connect, parsed.password)
        ctx.pine_slot = parsed.pine_slot
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        game_task = asyncio.create_task(game_loop(ctx), name="PCSX2 loop")
        await ctx.exit_event.wait()
        ctx.server_address = None
        await ctx.shutdown()
        await game_task

    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(main())
    colorama.deinit()


if __name__ == "__main__":
    launch_client()
