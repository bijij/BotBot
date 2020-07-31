import datetime

from collections import namedtuple
from io import BytesIO
from functools import partial
from typing import List, Optional, Set

import asyncpg
import numpy

from PIL import Image, ImageDraw, ImageFont

import discord
from discord.ext import commands, tasks

from bot import BotBase, Context, ConnectionContext


IMAGE_SIZE = 2970
FINAL_SIZE = 1024
SUPERSAMPLE = IMAGE_SIZE / FINAL_SIZE

ONE_DAY = 60 * 60 * 24

COLOURS = {
    None: (0, 0, 0, 0),
    discord.Status.online: (67, 181, 129, 255),
    discord.Status.offline: (116, 127, 141, 255),
    discord.Status.idle: (250, 166, 26, 255),
    discord.Status.dnd: (240, 71, 71, 255)
}

LogEntry = namedtuple('LogEntry', 'status duration')


def start_of_day(dt: datetime.datetime) -> datetime.datetime:
    return datetime.datetime.combine(dt, datetime.time())


async def get_status_log(user: discord.User, connection: asyncpg.Connection, *, days: int = 30) -> List[LogEntry]:
    records = await connection.fetch(f'SELECT * FROM status_log.log WHERE user_id = $1\
        AND "timestamp" > CURRENT_DATE - INTERVAL \'{days} days\' ORDER BY "timestamp" ASC', user.id)

    if not records:
        return list()

    # Add padding for missing data
    status_log = [
        LogEntry(status=None, duration=(records[0]['timestamp'] - start_of_day(records[0]['timestamp'])).total_seconds())
    ]

    for i, record in enumerate(records[:-1]):
        status_log.append(
            LogEntry(status=discord.Status(record['status']), duration=(records[i + 1]['timestamp'] - record['timestamp']).total_seconds())
        )

    return status_log


def draw_status_log(status_log: List[LogEntry], *, timezone: datetime.timezone = datetime.timezone.utc, show_dates: bool = False) -> BytesIO:

    # Setup Base Image
    image = Image.new('RGBA', (IMAGE_SIZE * 30, 1))
    draw = ImageDraw.Draw(image)

    day_width = IMAGE_SIZE / (60 * 60 * 24)

    now = datetime.datetime.now(timezone)
    timezone_offset = int(now.utcoffset().total_seconds())
    time_offset = 60 * 60 * timezone_offset
    total_duration = 0

    # Draw status log entries
    for status, duration in status_log:
        total_duration += duration
        new_time_offset = time_offset + duration

        start_x = round(time_offset * day_width)
        end_x = round(new_time_offset * day_width)
        draw.rectangle(((start_x, 0), (end_x, 1)), fill=COLOURS[status])

        time_offset = new_time_offset

    # Reshape Image
    pixels = numpy.array(image)
    # pixels = pixels[:, IMAGE_SIZE:]
    pixels = pixels.reshape(30, IMAGE_SIZE, 4)
    pixels = pixels.repeat(IMAGE_SIZE // 30, 0)
    image = Image.fromarray(pixels, 'RGBA')
    draw = ImageDraw.Draw(image)

    # Add date labels
    if show_dates:
        font = ImageFont.truetype('res/roboto-bold.ttf', IMAGE_SIZE // 50)

        date = now - datetime.timedelta(seconds=total_duration)
        for day in range(int(total_duration // ONE_DAY) + 1):
            y_offset = (IMAGE_SIZE // 30 * day) + IMAGE_SIZE // 200
            draw.text((IMAGE_SIZE // 100, y_offset), date.strftime('%b. %d'), font=font, align='left', fill=(255, 255, 255, 255))
            date = date + datetime.timedelta(days=1)

    # Apply AA
    image = image.resize((int(IMAGE_SIZE // SUPERSAMPLE),) * 2, resample=Image.LANCZOS)

    # Return as BytesIO
    image_fp = BytesIO()
    image.save(image_fp, format='png')

    image_fp.seek(0)
    return image_fp


class StatusLogging(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

        self._opted_in: Set[int] = set()

        self._status_logging_task.add_exception_type(asyncpg.PostgresConnectionError)
        self._status_logging_task.start()

    def cog_unload(self):
        self._status_logging_task.stop()

    @commands.group(name='logging')
    async def logging(self, ctx: Context):
        """Status logging management commands."""
        pass

    @logging.command(name='start')
    async def logging_start(self, ctx: Context):
        """Opt into status logging."""
        async with ctx.db as connection:
            opt_in_status = await connection.fetchrow('SELECT * FROM status_log.opt_in_status WHERE user_id = $1', ctx.author.id)
            if opt_in_status is not None:
                raise commands.BadArgument('You have already opted into status logging.')

            await connection.execute('INSERT INTO status_log.opt_in_status VALUES ($1, $2)', ctx.author.id, False)
            self._opted_in.add(ctx.author.id)

        await ctx.tick()

    @logging.command(name='stop')
    async def logging_stop(self, ctx: Context):
        """Opt out of logging."""
        async with ctx.db as connection:
            opt_in_status = await connection.fetchrow('SELECT * FROM status_log.opt_in_status WHERE user_id = $1', ctx.author.id)
            if opt_in_status is None:
                raise commands.BadArgument('You have not opted in to status logging.')

            await connection.execute('DELETE FROM status_log.opt_in_status WHERE user_id = $1', ctx.author.id)
            self._opted_in.remove(ctx.author.id)

        await ctx.tick()

    @logging.command(name='public')
    async def logging_public(self, ctx: Context, public: bool):
        """Set your status log visibility preferences."""
        async with ctx.db as connection:
            opt_in_status = await connection.fetchrow('SELECT * FROM status_log.opt_in_status WHERE user_id = $1', ctx.author.id)
            if opt_in_status is None:
                raise commands.BadArgument('You have not opted in to status logging.')

            await connection.execute('UPDATE status_log.opt_in_status SET public = $2 WHERE user_id = $1', ctx.author.id, public)

        await ctx.tick()

    @commands.command(name='status_log', aliases=['sl'])
    async def status_log(self, ctx: Context, user: Optional[discord.User] = None, show_dates: bool = False):
        """Display a status log.

        `user`: The user who's status log to look at, defaults to you.
        `show_dates`: Sets whether date labels should be shown, defaults to False.
        """
        user = user or ctx.author

        async with ctx.db as connection:

            opt_in_status = await connection.fetchrow('SELECT * FROM status_log.opt_in_status WHERE user_id = $1', user.id)
            if opt_in_status is None:
                raise commands.BadArgument(f'User "{user}" has not opted in for status logging.')

            if user != ctx.author and not opt_in_status['public']:
                raise commands.BadArgument(f'User "{user}" has not made their status log public.')

            data = await get_status_log(user, connection, days=30)

            if not data:
                raise commands.BadArgument(f'User "{user}" currently has not status log data, please try again later.')

        draw_call = partial(draw_status_log, data, timezone=datetime.timezone.utc, show_dates=show_dates)
        image = await self.bot.loop.run_in_executor(None, draw_call)

        await ctx.send(file=discord.File(image, f'{user.id}_status_{ctx.message.created_at}.png'))

    @commands.command(name='vaccum_status_log')
    @commands.is_owner()
    async def vaccum_status_log(self, ctx: Context, days: int = 35):
        """Remove entries from the status log older than n days."""
        raise commands.BadArgument('This Command is not yet implemented.')

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.status == after.status:
            return

        if before.id not in self._opted_in:
            return

        if after.status not in COLOURS:
            return

        if after.status == self.bot._last_status.get(after.id):
            return

        self.bot._status_log.append((after.id, datetime.datetime.utcnow(), after.status.name))
        self.bot._last_status[after.id] = after.status

    @tasks.loop(seconds=60)
    async def _status_logging_task(self):
        async with ConnectionContext(pool=self.bot.pool) as connection:
            await connection.executemany('INSERT INTO status_log.log VALUES ($1, $2, $3)', self.bot._status_log)
            self.bot._status_log = list()

    @_status_logging_task.before_loop
    async def _before_status_logging_task(self):
        await self.bot.wait_until_ready()

        async with ConnectionContext(pool=self.bot.pool) as connection:
            records = await connection.fetch('SELECT * FROM status_log.opt_in_status')

        for record in records:
            self._opted_in.add(record['user_id'])


def setup(bot: BotBase):
    if not hasattr(bot, '_status_log'):
        bot._status_log = list()
        bot._last_status = dict()

    bot.add_cog(StatusLogging(bot))
