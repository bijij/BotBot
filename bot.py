import datetime
from collections import defaultdict

import discord
from discord.ext import commands
from ditto import BotBase as DittoBase, Context, CONFIG

try:
    from cogs.memes.bot_status import get_status
except ImportError:

    def get_status(time: datetime.datetime):
        return discord.Status.online


class BotBase(DittoBase):
    def __init__(self) -> None:
        status = get_status(datetime.datetime.now(datetime.timezone.utc))
        self.whitelisted_users: dict[int, set[int]] = {}

        super().__init__(status=status)

    async def process_commands(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.channel.id in self.whitelisted_users:
            if message.author.id not in self.whitelisted_users[message.channel.id]:
                return

        ctx = await self.get_context(message, cls=Context)
        await self.invoke(ctx)


class Bot(BotBase, commands.Bot):
    ...


class AutoShardedBot(BotBase, commands.AutoShardedBot):
    ...
