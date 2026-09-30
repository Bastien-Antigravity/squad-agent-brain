#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS:
Provides the dynamic Telegram TeleClient controller for Squad Control.
Exposes submenus to switch active modes and execute subcommands.

DATA FLOW:
1. Instantiates TeleClient with configuration and logger.
2. Rebuilds dynamic interactive Telegram menu tree (Status, Mode Switch, Subcommands).
3. Receives interactive button clicks and commands from authorized Telegram users.
4. Executes controller actions and reports telemetry back to Telegram.

KEY PARAMETERS:
- tc: TeleClient instance.
- controller: CommandController singleton instance.
- logger: UniLog or compatible logging handle.
- config: Distributed configuration handle.
"""

import asyncio
from typing import Any, Optional
from microservice_toolbox.teleremote import TeleClient, Action

# -----------------------------------------------------------------------------

class MenuManager:
    """Orchestrates dynamic rebuild operations for the Squad Control Telegram menu."""

    # -----------------------------------------------------------------------------

    def __init__(self, tc: TeleClient, controller: Any, logger: Any, config: Any = None):
        self.tc = tc
        self.controller = controller
        self.logger = logger
        self.config = config

    # -----------------------------------------------------------------------------

    def rebuild_menu(self):
        """Pulls status, modes, and commands to rebuild the Telegram menu."""
        self.logger.info("Squad Telegram Menu: Rebuilding dynamic action tree...")

        actions = []

        # 1. Status Check Action
        async def handle_status(user_input: str) -> None:
            try:
                status = await self.controller.get_status()
                mode = await self.controller.get_active_mode()
                mode_name, _ = self.controller.get_mode_details(mode)
                msg = f"🚀 Squad Status: {status.get('status', 'running')}\n"
                msg += f"- Healthy: {status.get('healthy', True)}\n"
                msg += f"- Active Mode: {mode_name} (Mode {mode})\n"
                msg += f"- Version: {status.get('version', '1.0.0')}"
                await self.tc.send_telemetry(msg)
            except Exception as err:
                await self.tc.send_telemetry(f"❌ Error fetching status: {err}")

        actions.append(Action(label="ℹ️ Status / Mode", callback=handle_status))

        # 2. Mode Switch Submenu
        mode_submenu = []
        from src.core.switch_mode import MODES
        for mode_key, (mode_name, mode_desc) in MODES.items():
            def make_mode_callback(m_key, m_name):
                async def mode_cb(user_input: str) -> None:
                    await self.tc.send_telemetry(f"⚡ Switching active mode to {m_name}...")
                    success, msg = await self.controller.switch_mode(m_key)
                    if success:
                        await self.tc.send_telemetry(f"✅ {msg}")
                        self.rebuild_menu()
                    else:
                        await self.tc.send_telemetry(f"❌ Failed: {msg}")
                return mode_cb
            mode_submenu.append(Action(label=mode_name, callback=make_mode_callback(mode_key, mode_name)))

        actions.append(Action(label="🕹️ Switch Mode", sub_menu=mode_submenu))

        # 3. Command Execution Submenu
        command_submenu = []
        commands = self.controller.list_commands()
        for cmd in commands:
            cmd_name = cmd["name"]
            cmd_desc = cmd["description"]
            
            if cmd_name == "start-squad":
                continue

            def make_cmd_callback(c_name):
                async def cmd_cb(user_input: str) -> None:
                    await self.tc.send_telemetry(f"🚀 Launching command {c_name} in the background...")
                    success, msg = await self.controller.run_subcommand_async(c_name, [])
                    if success:
                        await self.tc.send_telemetry(f"✅ {msg}")
                    else:
                        await self.tc.send_telemetry(f"❌ Failed: {msg}")
                return cmd_cb

            command_submenu.append(Action(label=f"Run {cmd_name}", callback=make_cmd_callback(cmd_name)))

        actions.append(Action(label="🚀 Execute Command", sub_menu=command_submenu))

        self.tc.update_actions(actions)

        # Trigger background transmission of the updated UI menu state
        async def push():
            await self.tc.push_menu_update()

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(push())
        except RuntimeError:
            pass

# -----------------------------------------------------------------------------

def SetupTelegram(config: Any, controller: Any, logger: Any) -> Optional[TeleClient]:
    """Initializes dynamic Tele-Remote client, binds updates, and registers exit handlers."""
    try:
        tele_addr = config.get_listen_addr("tele_remote")
        host, port_str = tele_addr.split(":")
        port = int(port_str)
    except Exception as e:
        logger.info(f"TeleRemote capability not configured or could not resolve address ({e}). Skipping SetupTelegram.")
        return None

    logger.info(f"📡 Initializing dynamic Telegram Client for Base Scripts connecting to {host}:{port}...")
    tc = TeleClient("Squad Control", host, port, logger)
    mgr = MenuManager(tc, controller, logger, config)

    # Build initial menu
    mgr.rebuild_menu()

    async def start_tc():
        await tc.start()

    loop = asyncio.get_event_loop()
    if loop.is_running():
        loop.create_task(start_tc())
    else:
        loop.run_until_complete(start_tc())

    import atexit
    atexit.register(lambda: loop.run_until_complete(tc.close()))

    return tc
