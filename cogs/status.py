import datetime

from collections import Counter, namedtuple
from io import BytesIO
from functools import partial
from typing import Dict, List, Optional, Set, Tuple

import asyncpg
import numpy

from PIL import Image, ImageChops, ImageDraw, ImageFont

import discord
from discord.ext import commands, tasks

from bot import BotBase, Context, ConnectionContext


IMAGE_SIZE = 2970
PIE_SIZE = 2048
FINAL_SIZE = 1024
SUPERSAMPLE = IMAGE_SIZE / FINAL_SIZE

ONE_DAY = 60 * 60 * 24

WHITE = (255, 255, 255, 255)

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


async def get_status_records(user: discord.User, conn: asyncpg.Connection, *, days: int = 30) -> List[asyncpg.Record]:
    return await conn.fetch(f'SELECT * FROM logging.log WHERE user_id = $1\
        AND "timestamp" > CURRENT_DATE - INTERVAL \'{days} days\' ORDER BY "timestamp" ASC', user.id)


async def get_status_totals(user: discord.User, conn: asyncpg.Connection, *, days: int = 30) -> Counter:
    records = await get_status_records(user, conn, days=days)

    if not records:
        return Counter()

    status_totals = Counter()

    total_duration = (records[-1]['timestamp'] - records[0]['timestamp']).total_seconds()

    for i, record in enumerate(records[:-1]):
        status_totals[discord.Status(record['status'])] += (records[i + 1]['timestamp'] - record['timestamp']).total_seconds() / total_duration

    return status_totals


async def get_status_log(user: discord.User, conn: asyncpg.Connection, *, days: int = 30) -> List[LogEntry]:
    records = await get_status_records(user, conn, days=days)

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


def base_image(width: int = IMAGE_SIZE, height: int = IMAGE_SIZE) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new('RGBA', (width, height))
    draw = ImageDraw.Draw(image)

    return image, draw


def resample(image: Image.Image) -> Image.Image:
    return image.resize((int(IMAGE_SIZE // SUPERSAMPLE),) * 2, resample=Image.LANCZOS)


def as_bytes(image: Image.Image) -> BytesIO:
    image_fp = BytesIO()
    image.save(image_fp, format='png')

    image_fp.seek(0)
    return image_fp


def add(*tuples: Tuple[int, ...]) -> Tuple[int, ...]:
    return tuple(map(sum, zip(*tuples)))


def draw_status_pie(status_totals: Counter, avatar_fp: Optional[BytesIO], *, show_totals: bool = True) -> BytesIO:

    image, draw = base_image()

    # Make pie max size if no totals
    if not show_totals:
        pie_size = IMAGE_SIZE
        pie_offset = (0,) * 2
    else:
        pie_size = PIE_SIZE
        pie_offset = (0, (IMAGE_SIZE - pie_size) // 2)

    # Draw status pie
    pie_0 = add((0,) * 2, pie_offset)
    pie_1 = add((pie_size,) * 2, pie_offset)

    degrees = 270.0
    for status, percentage in status_totals.most_common():
        start = degrees
        degrees += 360 * percentage
        draw.pieslice((pie_0, pie_1), start, degrees, fill=COLOURS[status])

    if avatar_fp is not None:
        # Load avatar image
        avatar = Image.open(avatar_fp)
        if avatar.mode != 'RGBA':
            avatar = avatar.convert('RGBA')
        avatar = avatar.resize((int(pie_size // 1.5),) * 2, resample=Image.LANCZOS)

        # Apply circular mask to image
        _, _, _, alpha = avatar.split()
        if alpha.mode != 'L':
            alpha = alpha.convert('L')

        mask = Image.new('L', avatar.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + avatar.size, fill=255)

        mask = ImageChops.darker(mask, alpha)
        avatar.putalpha(mask)

        # Overlay avatar
        image.paste(avatar, add((pie_size // 6,) * 2, pie_offset), avatar)

    # Add status percentages
    if show_totals:
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('res/roboto-bold.ttf', IMAGE_SIZE // 20)

        x_offset = IMAGE_SIZE // 4 * 3
        y_offset = IMAGE_SIZE // 3
        circle_size = (IMAGE_SIZE // 30,) * 2

        for status, percentage in status_totals.most_common():
            offset = (x_offset, y_offset)

            draw.ellipse(offset + add(offset, circle_size), fill=COLOURS[status])
            draw.text((x_offset + IMAGE_SIZE // 20, y_offset - IMAGE_SIZE // 60), f'{percentage:.2%}', font=font, align='left', fill=WHITE)

            y_offset += IMAGE_SIZE // 8

    return as_bytes(resample(image))


def draw_status_log(status_log: List[LogEntry], *, timezone: datetime.timezone = datetime.timezone.utc, show_dates: bool = False) -> BytesIO:

    image, draw = base_image(IMAGE_SIZE * 30, 1)

    # Set consts
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
        x_offset = IMAGE_SIZE // 100
        y_offset = IMAGE_SIZE // 200

        date = now - datetime.timedelta(seconds=total_duration)
        for day in range(int(total_duration // ONE_DAY) + 1):
            draw.text((x_offset, y_offset), date.strftime('%b. %d'), font=font, align='left', fill=WHITE)
            y_offset += IMAGE_SIZE // 30
            date += datetime.timedelta(days=1)

    return as_bytes(resample(image))


async def is_opted_in(ctx: Context, conn: asyncpg.Connection):
    opt_in_status = await conn.fetchrow('SELECT * FROM logging.opt_in_status WHERE user_id = $1', ctx.author.id)
    if opt_in_status is None:
        raise commands.BadArgument(f'You have not opted in to status logging. You can do so with `{ctx.bot.prefix}logging start`')


async def is_not_opted_in(ctx: Context, conn: asyncpg.Connection):
    opt_in_status = await conn.fetchrow('SELECT * FROM logging.opt_in_status WHERE user_id = $1', ctx.author.id)
    if opt_in_status is not None:
        raise commands.BadArgument('You have already opted into status logging.')


async def is_public(ctx: Context, user: discord.User, conn: asyncpg.Connection):
    opt_in_status = await conn.fetchrow('SELECT * FROM logging.opt_in_status WHERE user_id = $1', user.id)
    if opt_in_status is None:
        raise commands.BadArgument(f'User "{user}" has not opted in for status logging.')

    if user != ctx.author and not opt_in_status['public']:
        raise commands.BadArgument(f'User "{user}" has not made their status log public.')


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
        async with ctx.db as conn:
            await is_not_opted_in(ctx, conn)
            await conn.execute('INSERT INTO logging.opt_in_status VALUES ($1, $2)', ctx.author.id, False)
            self._opted_in.add(ctx.author.id)

        await ctx.tick()

    @logging.command(name='stop')
    async def logging_stop(self, ctx: Context):
        """Opt out of logging."""
        async with ctx.db as conn:
            await is_opted_in(ctx, conn)
            await conn.execute('DELETE FROM logging.opt_in_status WHERE user_id = $1', ctx.author.id)
            self._opted_in.remove(ctx.author.id)

        await ctx.tick()

    @logging.command(name='public')
    async def logging_public(self, ctx: Context, public: bool):
        """Set your status log visibility preferences."""
        async with ctx.db as conn:
            await is_opted_in(ctx, conn)
            await conn.execute('UPDATE logging.opt_in_status SET public = $2 WHERE user_id = $1', ctx.author.id, public)

        await ctx.tick()

    @commands.command(name='status_pie', aliases=['sp'])
    async def status_pie(self, ctx: Context, user: Optional[discord.User] = None, show_totals: bool = True):
        """Display a status pie.

        `user`: The user who's status log to look at, defaults to you.
        `show_totals`: Sets whether status percentages should be shown, defaults to True.
        """
        user = user or ctx.author

        async with ctx.db as conn:
            await is_public(ctx, user, conn)
            data = await get_status_totals(user, conn, days=30)

            if not data:
                raise commands.BadArgument(f'User "{user}" currently has no status log data, please try again later.')

        avatar_fp = BytesIO()
        await user.avatar_url_as(format='png', size=PIE_SIZE // 2).save(avatar_fp)

        draw_call = partial(draw_status_pie, data, avatar_fp, show_totals=show_totals)
        image = await self.bot.loop.run_in_executor(None, draw_call)

        await ctx.send(file=discord.File(image, f'{user.id}_status_{ctx.message.created_at}.png'))

    @commands.command(name='status_log', aliases=['sl'])
    async def status_log(self, ctx: Context, user: Optional[discord.User] = None, show_dates: bool = False):
        """Display a status log.

        `user`: The user who's status log to look at, defaults to you.
        `show_dates`: Sets whether date labels should be shown, defaults to False.
        """
        user = user or ctx.author

        async with ctx.db as conn:
            await is_public(ctx, user, conn)
            data = await get_status_log(user, conn, days=30)

            if not data:
                raise commands.BadArgument(f'User "{user}" currently has no status log data, please try again later.')

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

        self.bot._logging.append((after.id, datetime.datetime.utcnow(), after.status.name))
        self.bot._last_status[after.id] = after.status

    @tasks.loop(seconds=60)
    async def _status_logging_task(self):
        async with ConnectionContext(pool=self.bot.pool) as conn:
            await conn.executemany('INSERT INTO logging.log VALUES ($1, $2, $3)', self.bot._status_log)
            self.bot._status_log = list()

    @_status_logging_task.before_loop
    async def _before_status_logging_task(self):
        await self.bot.wait_until_ready()

        async with ConnectionContext(pool=self.bot.pool) as conn:
            records = await conn.fetch('SELECT * FROM logging.opt_in_status')

        for record in records:
            self._opted_in.add(record['user_id'])


def setup(bot: BotBase):
    if not hasattr(bot, '_status_log'):
        bot._status_log = list()
        bot._last_status = dict()

    bot.add_cog(StatusLogging(bot))
