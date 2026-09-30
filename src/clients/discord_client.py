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
        self.client: Optional[Any] = None
        if HAS_DISCORD and self.token:
            self._setup_bot()

    # -----------------------------------------------------------------------------------------------

    def _resolve_token(self) -> Optional[str]:
        """Resolves the Discord bot token from environment or settings file."""
        token = getenv("DISCORD_BOT_TOKEN")
        if not token:
            settings = self.config.data.get("capabilities", {}).get("discord", {})
            token = settings.get("bot_token")
        if token and token.startswith("ENC(") and hasattr(self.config, "decrypt_secret"):
            token = self.config.decrypt_secret(token)
        return token

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

        # -------------------------------------------------------------------------------------------
        @self.client.event
        async def on_message(message: Any) -> None:
            # Prevent bot self-triggering
            if message.author == self.client.user:
                return

            # Commands start with a slash or specific mention prefix
            if message.content.startswith("/") or self.client.user.mentioned_in(message):
                clean_msg = message.content
                if message.content.startswith("/"):
                    clean_msg = message.content[1:]
                else:
                    # Strip mention syntax
                    clean_msg = message.content.replace("<@{0.user.id}>".format(self.client), "").strip()

                session_id = "discord_{0}".format(message.channel.id)
                self.logger.info("DiscordClient : Message received from {0.author} : {1}".format(message.author, clean_msg))

                # Route user payload to unified controller
                try:
                    res = self.controller.process_message(
                        channel="DISCORD_{0}".format(message.channel.name or message.channel.id),
                        session_id=session_id,
                        user_msg=clean_msg
                    )
                    reply = res.get("answer", "No response from squad.")
                    await message.reply(reply)
                except Exception as ex:
                    self.logger.error("DiscordClient : Error processing channel payload: {0}".format(ex))
                    await message.reply("Error: {0}".format(ex))

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

def main() -> None:
    """Invokes and starts the Discord Gateway Client adapter."""
    import src.bootstrap as bootstrap
    from core.controller import CommandController

    controller = CommandController(config=bootstrap.config, logger=bootstrap.logger)
    client_adapter = DiscordClient(config=bootstrap.config, logger=bootstrap.logger, controller=controller)
    client_adapter.start()
