import datetime

from collections import Counter
from collections import Iterable
from io import BytesIO, StringIO
from functools import partial
from typing import cast, NamedTuple, Optional

import asyncpg
import numpy

from ics import Calendar, Event
from PIL import Image, ImageChops, ImageDraw, ImageFont

import discord
from discord.ext import commands

from ditto import BotBase, Cog, Context
from ditto.db import TimeZones
from ditto.types.converters import PosixFlags
from ditto.utils.strings import utc_offset

from .core import COLOURS
from .db import OptInStatus, StatusLog

MIN_DAYS = 7

IMAGE_SIZE = 4096
DOWNSAMPLE = 2
FINAL_SIZE = IMAGE_SIZE / DOWNSAMPLE

ONE_DAY = 60 * 60 * 24
ONE_HOUR = IMAGE_SIZE // 24

WHITE = (255, 255, 255, 255)
OPAQUE = (255, 255, 255, 128)
TRANSLUCENT = (255, 255, 255, 32)


class LogEntry(NamedTuple):
    status: Optional[str]
    start: datetime.datetime
    duration: datetime.timedelta


class StatusPieOptions(PosixFlags):
    show_totals: bool = commands.flag(aliases=["totals"], default=True)
    num_days: int = commands.flag(aliases=["days"], default=30)


class StatusLogOptions(PosixFlags):
    timezone: Optional[float] = commands.flag(aliases=["tz"])
    show_labels: bool = commands.flag(aliases=["labels"], default=True)
    num_days: int = commands.flag(aliases=["days"], default=30)
    _square: bool = True


def start_of_day(dt: datetime.datetime) -> datetime.datetime:
    return datetime.datetime.combine(dt, datetime.time()).astimezone(datetime.timezone.utc)


async def get_status_records(
    connection: asyncpg.Connection, user: discord.User, *, days: int = 30
) -> Iterable[asyncpg.Record]:
    return await StatusLog.fetch_where(
        connection,
        f"user_id = $1 AND \"timestamp\" > CURRENT_DATE - INTERVAL '{days} days'",
        user.id,
        order_by=(StatusLog.timestamp, "ASC"),
    )


async def get_status_totals(connection: asyncpg.Connection, user: discord.User, *, days: int = 30) -> Counter:
    records = list(await get_status_records(connection, user, days=days))

    if not records:
        return Counter()

    status_totals = Counter()  # type: ignore

    total_duration = (records[-1]["timestamp"] - records[0]["timestamp"]).total_seconds()

    for i, record in enumerate(records[:-1]):
        status_totals[record["status"]] += (
            records[i + 1]["timestamp"] - record["timestamp"]
        ).total_seconds() / total_duration

    return status_totals


async def get_status_log(
    connection: asyncpg.Connection,
    user: discord.User,
    *,
    days: int = 30,
) -> list[LogEntry]:
    status_log: list[LogEntry] = []

    # Fetch records from DB
    records = list(await get_status_records(connection, user, days=days))
    if not records:
        return status_log

    # Add padding for missing data
    records.insert(0, (None, start_of_day(records[0]["timestamp"]), None))
    records.append((None, discord.utils.utcnow(), None))

    # Add in bulk of data
    for i, (_, start, status) in enumerate(records[:-1]):
        _, end, _ = records[i + 1]
        status_log.append(LogEntry(status, start, end - start))

    return status_log


def base_image(width: int = IMAGE_SIZE, height: int = IMAGE_SIZE) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)

    return image, draw  # type: ignore


def resample(image: Image.Image) -> Image.Image:
    return image.resize((image.width // DOWNSAMPLE, image.height // DOWNSAMPLE), resample=Image.LANCZOS)  # type: ignore


def as_bytes(image: Image.Image) -> BytesIO:
    image_fp = BytesIO()
    image.save(image_fp, format="png")

    image_fp.seek(0)
    return image_fp


def add(*tuples: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(map(sum, zip(*tuples)))  # type: ignore


def draw_status_pie(status_totals: Counter, avatar_fp: Optional[BytesIO], *, show_totals: bool = True) -> BytesIO:

    image, draw = base_image()

    # Make pie max size if no totals
    if not show_totals:
        pie_size = IMAGE_SIZE
        pie_offset = (0,) * 2
    else:
        pie_size = int(IMAGE_SIZE * 0.66)
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
        if avatar.mode != "RGBA":
            avatar = avatar.convert("RGBA")
        avatar = avatar.resize((int(pie_size // 1.5),) * 2, resample=Image.LANCZOS)

        # Apply circular mask to image
        _, _, _, alpha = avatar.split()
        if alpha.mode != "L":
            alpha = alpha.convert("L")

        mask = Image.new("L", avatar.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + avatar.size, fill=255)

        mask = ImageChops.darker(mask, alpha)
        avatar.putalpha(mask)

        # Overlay avatar
        image.paste(avatar, add((pie_size // 6,) * 2, pie_offset), avatar)

    # Add status percentages
    if show_totals:
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("res/roboto-bold.ttf", IMAGE_SIZE // 20)

        x_offset = IMAGE_SIZE // 4 * 3
        y_offset = IMAGE_SIZE // 3
        circle_size = (IMAGE_SIZE // 30,) * 2

        for status, percentage in status_totals.most_common():
            offset = (x_offset, y_offset)

            draw.ellipse(offset + add(offset, circle_size), fill=COLOURS[status])
            draw.text(
                (x_offset + IMAGE_SIZE // 20, y_offset - IMAGE_SIZE // 60),
                f"{percentage:.2%}",
                font=font,
                align="left",
                fill=WHITE,
            )

            y_offset += IMAGE_SIZE // 8

    return as_bytes(resample(image))


def draw_status_log(
    status_log: list[LogEntry],
    *,
    timezone: datetime.tzinfo = datetime.timezone.utc,
    show_labels: bool = False,
    num_days: int = 30,
    square: bool = True,
) -> BytesIO:

    row_count = 1 + num_days + show_labels
    image, draw = base_image(IMAGE_SIZE * row_count, 1)

    # Set consts
    day_width = IMAGE_SIZE / (60 * 60 * 24)
    if square:
        day_height = IMAGE_SIZE // row_count
    else:
        day_height = IMAGE_SIZE // 31 + show_labels

    image_height = round(day_height * row_count)

    now = datetime.datetime.now(timezone)
    time_offset = now.utcoffset().total_seconds()  # type: ignore
    total_duration = 0.0

    if show_labels:
        time_offset += 60 * 60 * 24

    # Draw status log entries
    for status, _, timespan in status_log:
        duration: float = timespan.total_seconds()
        total_duration += duration
        new_time_offset = time_offset + duration

        start_x = round(time_offset * day_width)
        end_x = round(new_time_offset * day_width)
        draw.rectangle(((start_x, 0), (end_x, 1)), fill=COLOURS[status])

        time_offset = new_time_offset

    # Reshape Image
    pixels = numpy.array(image)
    # pixels = pixels[:, IMAGE_SIZE:]
    pixels = pixels.reshape(row_count, IMAGE_SIZE, 4)
    pixels = pixels.repeat(day_height, 0)
    image = Image.fromarray(pixels, "RGBA")

    if show_labels:
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Set offsets based on font size
        font = ImageFont.truetype("res/roboto-bold.ttf", IMAGE_SIZE // int(1.66 * (num_days if square else 30)))
        text_half_width, text_height = draw.textsize("ｱ" * 2, font=font)
        height_offset = (day_height - text_height) // 2

        x_offset = text_half_width
        y_offset = day_height

        time = start_of_day(now)
        date = now - datetime.timedelta(seconds=total_duration)

        # Add weekend signifiers
        for _ in range(int(total_duration // ONE_DAY) + 2):  # 2 because of timezone offset woes

            if date.weekday() == 5:
                draw.rectangle(
                    (0, y_offset, IMAGE_SIZE, y_offset + (2 * day_height)),
                    fill=TRANSLUCENT,
                )

            y_offset += day_height
            date += datetime.timedelta(days=1)

        y_offset = day_height
        date = now - datetime.timedelta(seconds=total_duration)

        # Add timezone label
        draw.text(
            (x_offset, height_offset),
            utc_offset(timezone),
            font=font,
            align="left",
            fill="WHITE",
        )

        # Add hour lines
        for i in range(1, 24):
            x_offset = ONE_HOUR * i
            colour = WHITE if not i % 6 else OPAQUE
            draw.line(
                (x_offset, day_height, x_offset, image_height),
                fill=colour,
                width=DOWNSAMPLE * 4,
            )

        image = Image.alpha_composite(image, overlay)
        draw = ImageDraw.Draw(image)

        # Add time labels
        for x_offset in (ONE_HOUR * 6, ONE_HOUR * 12, ONE_HOUR * 18):
            time += datetime.timedelta(hours=6)
            text_width, _ = draw.textsize(time.strftime("%H:00"), font=font)
            draw.text(
                (x_offset - (text_width // 2), height_offset),
                time.strftime("%H:00"),
                font=font,
                align="left",
                fill=WHITE,
            )

        # Add date labels
        x_offset = text_half_width
        for _ in range(int(total_duration // ONE_DAY) + 2):  # 2 because of timezone offset woes

            _, text_height = draw.textsize(date.strftime("%b. %d"), font=font)
            draw.text(
                (x_offset, y_offset + height_offset),
                date.strftime("%b. %d"),
                font=font,
                align="left",
                fill=WHITE,
            )
            y_offset += day_height
            date += datetime.timedelta(days=1)

    return as_bytes(resample(image))


def generate_status_calendar(status_log: list[LogEntry]) -> StringIO:
    calendar = Calendar()

    for status, start, duration in status_log:
        event = Event()
        event.name = f"User was {status}"
        event.begin = start.strftime("%Y-%m-%d %H:%M:%S")
        event.end = (start + duration).strftime("%Y-%m-%d %H:%M:%S")
        calendar.events.add(event)

    out = StringIO()
    out.writelines(calendar)
    out.seek(0)
    return out


class StatusLogging(Cog):
    def __init__(self, bot: BotBase):
        self.bot = bot

    @commands.command(name="status_pie", aliases=["sp"])
    async def status_pie(
        self,
        ctx: Context,
        user: Optional[discord.User] = None,
        *,
        flags: StatusPieOptions,
    ):
        """Display a status pie.

        `user`: The user who's status log to look at, defaults to you.
        `show_totals`: Sets whether status percentages should be shown, defaults to True.
        """
        user = cast(discord.User, user or ctx.author)

        if flags.num_days < MIN_DAYS:
            raise commands.BadArgument(f"You must display at least {MIN_DAYS} days.")

        async with ctx.typing():
            async with ctx.db as connection:
                await OptInStatus.is_public(connection, ctx, user)
                data = await get_status_totals(connection, user, days=flags.num_days)

                if not data:
                    raise commands.BadArgument(
                        f'User "{user}" currently has no status log data, please try again later.'
                    )

            avatar_fp = BytesIO()
            await user.avatar.replace(format="png", size=IMAGE_SIZE // 2).save(avatar_fp)

            draw_call = partial(draw_status_pie, data, avatar_fp, show_totals=flags.show_totals)
            image = await self.bot.loop.run_in_executor(None, draw_call)

            await ctx.send(file=discord.File(image, f"{user.id}_status_{ctx.message.created_at}.png"))

    @commands.group(name="status_log", aliases=["sl", "sc"], invoke_without_command=True)
    async def status_log(
        self,
        ctx: Context,
        user: Optional[discord.User] = None,
        *,
        flags: StatusLogOptions,
    ):
        """Display a status log.

        `user`: The user who's status log to look at, defaults to you.
        `--labels`: Sets whether date and time labels should be shown, defaults to False.
        `--timezone`: The timezone offset to use in hours, defaults to the users set timezone or UTC+0.
        `--days`: The number of days to fetch status log data for. Defaults to 30.
        """
        user = cast(discord.User, user or ctx.author)

        timezone_offset = flags.timezone

        if timezone_offset is not None and not -14 < timezone_offset < 14:
            raise commands.BadArgument("Invalid timezone offset passed.")

        async with ctx.db as connection:
            if timezone_offset is None:
                timezone = await TimeZones.get_timezone(connection, user) or datetime.timezone.utc
            else:
                timezone = datetime.timezone(datetime.timedelta(hours=timezone_offset))

            if flags.num_days < MIN_DAYS:
                raise commands.BadArgument(f"You must display at least {MIN_DAYS} days.")

            async with ctx.typing():
                await OptInStatus.is_public(connection, ctx, user)
                data = await get_status_log(connection, user, days=flags.num_days)

                if not data:
                    raise commands.BadArgument(
                        f'User "{user}" currently has no status log data, please try again later.'
                    )

            delta = (ctx.message.created_at - data[0].start).days
            days = max(min(flags.num_days, delta), MIN_DAYS)

            draw_call = partial(
                draw_status_log,
                data,
                timezone=timezone,
                show_labels=flags.show_labels,
                num_days=days,
                square=flags._square,
            )
            image = await self.bot.loop.run_in_executor(None, draw_call)

            await ctx.send(file=discord.File(image, f"{user.id}_status_{ctx.message.created_at}.png"))

    @status_log.command(name="calendar", aliases=["cal"])
    async def status_log_calendar(self, ctx: Context, user: Optional[discord.User] = None):
        """Output an `ical` format status log"""
        user = cast(discord.User, user or ctx.author)

        async with ctx.db as connection:
            await OptInStatus.is_public(connection, ctx, user)
            data = await get_status_log(connection, user, days=30)

            if not data:
                raise commands.BadArgument(f'User "{user}" currently has no status log data, please try again later.')

        calendar = generate_status_calendar(data)
        await ctx.send(file=discord.File(calendar, f"{user.id}_status_{ctx.message.created_at}.ical"))


def setup(bot: BotBase):
    bot.add_cog(StatusLogging(bot))
