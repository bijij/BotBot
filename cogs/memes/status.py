import asyncio
import datetime
import json

import discord
from discord.ext import commands, tasks

from cogs.logging.logging import Status_Log

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
    STATUS_MAP = data['data']

    SECONDS_PER_DAY = 60 * 60 * 24
    SEGMENT_DURATION = SECONDS_PER_DAY // len(STATUS_MAP[0])


def get_status(time: datetime.datetime):
    delta = time - START_TIME

    # If outside map
    if not 0 <= delta.days < len(STATUS_MAP):
        return discord.Status.online

    return STATUSES[STATUS_MAP[delta.days][delta.seconds // SEGMENT_DURATION]]


class StatusMeme(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.status_task.start()

    async def set_status(self):
        now = datetime.datetime.utcnow()
        status = get_status(now)
        await self.bot.change_presence(status=status)
        await Status_Log.insert(user_id=self.bot.user.id, timestamp=now, status=status.name)

    @tasks.loop(seconds=SEGMENT_DURATION)
    async def status_task(self):
        try:
            await self.set_status()
        except Exception:
            pass

    @status_task.before_loop
    async def before_status_task(self):

        # Wait for ready
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)  # bad 1006 protection

        # Set status
        await self.set_status()

        # SLEEP until next segment
        now = datetime.datetime.utcnow()
        timestamp = now.timestamp() + SEGMENT_DURATION - (now.timestamp() % SEGMENT_DURATION)
        next_segment = datetime.datetime.fromtimestamp(timestamp)
        await discord.utils.sleep_until(next_segment)

    def cog_unload(self):
        self.status_task.cancel()


def setup(bot):
    bot.add_cog(StatusMeme(bot))
