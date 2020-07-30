from contextlib import suppress
from typing import Union

import discord
from discord.ext import commands

from .db import ConnectionContext


class Context(commands.Context):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = ConnectionContext(pool=self.bot.pool)

    async def tick(self, *, message: discord.Message = None, emoji: Union[discord.Emoji, str] = "\N{WHITE HEAVY CHECK MARK}"):
        """Reacts to a message with a green tick."""
        message = message or self.message
        with suppress(discord.HTTPException):
            await message.add_reaction(emoji)
