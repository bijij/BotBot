from contextlib import suppress
from typing import Optional, Union

import discord
from discord.ext import commands

from donphan import MaybeAcquire


class Context(commands.Context):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.db = MaybeAcquire(pool=self.bot.pool)

    async def tick(self, *, message: Optional[discord.Message] = None, emoji: Union[discord.Emoji, str] = "\N{WHITE HEAVY CHECK MARK}"):
        """Reacts to a message with a green tick."""
        message = message or self.message
        with suppress(discord.HTTPException):
            await message.add_reaction(emoji)
