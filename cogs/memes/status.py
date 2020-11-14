import asyncio
import datetime
import json

import discord
from discord.ext import commands, tasks

STATUSES = {
    0: discord.Status.online,
    1: discord.Status.offline,
    2: discord.Status.idle,
    3: discord.Status.dnd
}

TEST_FILE = 'res/status_maps/test.json'
with open(TEST_FILE, 'r') as f:
    data = json.load(f)

    START_TIME = datetime.datetime.fromisoformat(data['start'])
    STATUS_MAP = data['map']


def get_status(time: datetime.datetime):
    delta = time - START_TIME

    # If outside map
    if not 0 <= delta.days < len(STATUS_MAP):
        return discord.Status.online

    return STATUSES[STATUS_MAP[delta.seconds // 3600]]


class StatusMeme(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def set_status(self):
        now = datetime.datetime.utcnow()
        await self.bot.change_presence(status=get_status(now))

    @tasks.loop(hours=1)
    async def status_task(self):
        try:
            await self.set_status()
        except Exception:
            pass

    @status_task.before_loop
    async def before_status_task(self):

        await self.bot.wait_until_ready()
        await asyncio.sleep(5)  # bad 1006 protection

        await self.set_status()

        now = datetime.datetime.utcnow()
        next_hour = now.replace(minute=0, second=0, microsecond=0)
        next_hour += datetime.timedelta(hours=1)

        await discord.utils.sleep_until(next_hour)


def setup(bot):
    bot.add_cog(StatusMeme(bot))
