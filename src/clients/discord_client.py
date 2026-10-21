#!/usr/bin/env python
# coding:utf-8

"""
ESSENTIAL PROCESS: DiscordClient
  Discord bot client adapter connecting Discord chat channels to the unified
  squad command controller.

DATA FLOW:
  1. Input:   Discord text channel message payloads.
  2. Logic:   Maps channel IDs to persistent session scopes and forwards
              payloads to CommandController.
  3. Output:  Sends the controller result message back to the originating Discord channel.

KEY PARAMETERS:
  - token:    Discord bot authentication token.
"""

import sys
from typing import Any, Optional
from os import getenv

try:
    import discord
    HAS_DISCORD = True
except ImportError:
    discord = None
    HAS_DISCORD = False

# -----------------------------------------------------------------------------------------------

class DiscordClient:
    """
    Discord bot client interface mapping channels to unified controller scopes.
    """

    def __init__(self, *, config: Any, logger: Any, controller: Any):
        self.config = config
        self.logger = logger
        self.controller = controller
        self.token = self._resolve_token()
        self.channel_id = self._resolve_channel_id()
        self.client: Optional[Any] = None
        if HAS_DISCORD and self.token:
            self._setup_bot()

    # -----------------------------------------------------------------------------------------------

    def _resolve_token(self) -> Optional[str]:
        """Resolves the Discord bot token from environment or settings file."""
        token = getenv("DISCORD_BOT_TOKEN")
        if not token and hasattr(self.config, "data"):
            squad_cfg = self.config.data.get("capabilities", {}).get("squad_agent", {})
            settings = squad_cfg.get("discord", {}) if isinstance(squad_cfg, dict) else {}
            if not settings:
                settings = self.config.data.get("capabilities", {}).get("discord", {})
            token = settings.get("bot_token") or settings.get("token")
        if token and "${" in token and "}" in token:
            import re
            m = re.search(r':-?([^}]+)', token)
            if m:
                token = m.group(1)
        if token and token.startswith("ENC(") and hasattr(self.config, "decrypt_secret"):
            token = self.config.decrypt_secret(token)
        return token.strip() if token else None

    # -----------------------------------------------------------------------------------------------

    def _resolve_channel_id(self) -> Optional[str]:
        """Resolves the designated Discord channel ID for squad chat monitoring."""
        ch_id = getenv("DISCORD_CHANNEL_ID")
        if not ch_id and hasattr(self.config, "data"):
            squad_cfg = self.config.data.get("capabilities", {}).get("squad_agent", {})
            settings = squad_cfg.get("discord", {}) if isinstance(squad_cfg, dict) else {}
            if not settings:
                settings = self.config.data.get("capabilities", {}).get("discord", {})
            ch_id = settings.get("channel_id")
        if ch_id and "${" in str(ch_id):
            import re
            m = re.search(r':-?([^}]+)', str(ch_id))
            if m:
                ch_id = m.group(1)
        return str(ch_id).strip() if ch_id else None

    # -----------------------------------------------------------------------------------------------

    async def _stream_squad_events_to_discord(self) -> None:
        """Subscribes to NATS/LocalEventBus squad chat topics and mirrors agent communication into Discord."""
        event_bus = getattr(self.controller, "event_bus", None)
        if not event_bus:
            from src.interfaces import LocalEventBus
            event_bus = LocalEventBus

        role_icons = {
            "orchestrator": "🤖",
            "developer": "🛠️",
            "qa": "🧪",
            "architect": "📐",
            "trader": "📈",
            "analyst": "📊",
            "docindexer": "📚",
            "purger": "🧹",
        }

        async def squad_event_callback(payload: dict) -> None:
            sender = payload.get("sender", "")
            # Filter out user messages to prevent echo loops
            if not sender or sender.lower() == "user":
                return

            content = payload.get("content", "")
            if not content:
                return

            try:
                ch = self.client.get_channel(int(self.channel_id))
                if not ch:
                    ch = await self.client.fetch_channel(int(self.channel_id))
                if ch:
                    icon = role_icons.get(sender.lower(), "🤖")
                    msg_text = f"{icon} **[{sender.upper()}]**\n{content}"
                    if len(msg_text) > 1950:
                        msg_text = msg_text[:1940] + "\n...[truncated]"
                    await ch.send(msg_text)
            except Exception as e:
                self.logger.warning(f"DiscordClient : Failed to relay squad event to Discord channel {self.channel_id}: {e}")

        import inspect
        res = event_bus.subscribe("bastien-antigravity.squad.chat", callback=squad_event_callback)
        if inspect.isawaitable(res):
            await res
        res_wildcard = event_bus.subscribe("bastien-antigravity.*.squad.chat", callback=squad_event_callback)
        if inspect.isawaitable(res_wildcard):
            await res_wildcard

    # -----------------------------------------------------------------------------------------------

    def _setup_bot(self) -> None:
        """Configures the discord.py client and registers handlers."""
        intents = discord.Intents.default()
        intents.message_content = True
        self.client = discord.Client(intents=intents)

        # -------------------------------------------------------------------------------------------
        @self.client.event
        async def on_ready() -> None:
            self.logger.info("DiscordClient : Logged in as {0.user}".format(self.client))
            if self.channel_id:
                self.logger.info(f"DiscordClient : Monitoring squad chat and mirroring to channel {self.channel_id}")
                import asyncio
                asyncio.create_task(self._stream_squad_events_to_discord())

        # -------------------------------------------------------------------------------------------
        @self.client.event
        async def on_message(message: Any) -> None:
            # Prevent bot self-triggering
            if message.author == self.client.user:
                return

            is_designated_channel = self.channel_id and str(message.channel.id) == str(self.channel_id)
            is_command = message.content.startswith("/") or self.client.user.mentioned_in(message)

            if is_designated_channel or is_command:
                clean_msg = message.content
                if message.content.startswith("/"):
                    clean_msg = message.content[1:]
                elif self.client.user.mentioned_in(message):
                    clean_msg = message.content.replace("<@{0.user.id}>".format(self.client), "").strip()

                session_id = f"discord_{message.channel.id}"
                self.logger.info(f"DiscordClient : User message received from {message.author} : {clean_msg}")

                # Publish directly onto NATS so all agents receive and process
                try:
                    await self.controller.publish_user_message(session_id, clean_msg)
                except Exception as ex:
                    self.logger.error(f"DiscordClient : Error publishing message onto squad event bus: {ex}")
                    await message.reply(f"Error: {ex}")

    # -----------------------------------------------------------------------------------------------

    def start(self) -> None:
        """Establishes connection to the Gateway."""
        if not HAS_DISCORD:
            self.logger.warning("DiscordClient : discord.py library is not installed in the python environment.")
            self.logger.info("💡 Suggestion: To use Discord features, run: pip install discord.py")
            return

        if not self.token:
            self.logger.warning("DiscordClient : DISCORD_BOT_TOKEN environment variable or config setting is missing.")
            return

        self.logger.info("DiscordClient : Starting bot Gateway connection...")
        try:
            self.client.run(self.token)
        except Exception as e:
            self.logger.error("DiscordClient : Failed to run Discord Client Gateway: {0}".format(e))

    # -----------------------------------------------------------------------------------------------

    async def start_async(self) -> None:
        """Asynchronously establishes connection to the Discord Gateway."""
        if not HAS_DISCORD:
            self.logger.warning("DiscordClient : discord.py library is not installed in the python environment.")
            return

        if not self.token:
            self.logger.warning("DiscordClient : DISCORD_BOT_TOKEN environment variable or config setting is missing.")
            return

        self.logger.info("DiscordClient : Starting bot Gateway connection asynchronously...")
        try:
            await self.client.start(self.token)
        except Exception as e:
            self.logger.error(f"DiscordClient : Failed to run Discord Client Gateway asynchronously: {e}")

# -----------------------------------------------------------------------------------------------

def main() -> None:
    """Invokes and starts the Discord Gateway Client adapter."""
    import src.bootstrap as bootstrap
    from core.controller import CommandController

    controller = CommandController(config=bootstrap.config, logger=bootstrap.logger)
    client_adapter = DiscordClient(config=bootstrap.config, logger=bootstrap.logger, controller=controller)
    client_adapter.start()

