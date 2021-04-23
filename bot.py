import datetime

# from ampharos import setup as setup_ampharos

import discord
from discord.ext import commands
from ditto import BotBase, Context, CONFIG

try:
    from cogs.memes.status import get_status
except ImportError:

    def get_status(_):
        return discord.Status.online


class BotBase(BotBase):
    def __init__(self) -> None:
        status = get_status(datetime.datetime.now(datetime.timezone.utc))
        self.whitelisted_users: set[int] = set()

        super().__init__(status=status)

    async def process_commands(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.channel == CONFIG.DPY_VOICE_GENERAL and message.author.id not in self.whitelisted_users:
            return

        ctx = await self.get_context(message, cls=Context)
        await self.invoke(ctx)

    async def setup_database(self) -> None:
        await super().setup_database()
        # await setup_ampharos()


class Bot(BotBase, commands.Bot):
    ...


class AutoShardedBot(BotBase, commands.AutoShardedBot):
    ...
