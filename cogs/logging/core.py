import datetime
import re

from contextlib import suppress
from typing import Literal, NamedTuple, Optional

import asyncpg
from donphan import MaybeAcquire

import discord
from discord.ext import commands, tasks

from ditto import BotBase, Cog, Context

from .db import MessageLog, MessageAttachments, MessageEditHistory, OptInStatus, Status, StatusLog

TEXT_FILE_REGEX = re.compile(r"^.*; charset=.*$")


COLOURS: dict[Optional[Status], tuple[int, int, int, int]] = {  # type: ignore
    None: (0, 0, 0, 0),
    Status.online: (55, 165, 92, 255),
    Status.offline: (116, 127, 141, 255),
    Status.idle: (250, 166, 26, 255),
    Status.dnd: (237, 66, 69, 255),
    Status.streaming: (89, 54, 149, 255),
}


COLOURS_OLD: dict[Optional[Status], tuple[int, int, int, int]] = {  # type: ignore
    Status.online: (67, 181, 129, 255),
    Status.dnd: (237, 66, 69, 255),
    Status.streaming: (89, 54, 149, 255),
}


class MessageLogEntry(NamedTuple):
    channel_id: int
    message_id: int
    guild_id: int
    user_id: int
    content: str
    is_nsfw: bool
    is_deleted: bool = False


class MessageDeleteLogEntry(NamedTuple):
    message_id: int


class MessageAttachmentLogEntry(NamedTuple):
    message_id: int
    attachment_id: int
    content: str


class MessageUpdateLogEntry(NamedTuple):
    message_id: int
    timestamp: datetime.datetime
    content: str


class StatusLogEntry(NamedTuple):
    user_id: int
    timestamp: datetime.datetime
    status: Status


class LoggingBot(BotBase):
    _logging: Literal[True]
    _message_log: list[MessageLogEntry]
    _message_delete_log: list[MessageDeleteLogEntry]
    _message_attachment_log: list[MessageAttachmentLogEntry]
    _message_update_log: list[MessageUpdateLogEntry]
    _status_log: list[StatusLogEntry]
    _last_status: dict[int, Status]


class Logging(Cog):
    def __init__(self, bot: LoggingBot):
        self.bot = bot

        self._opted_in: set[int] = set()
        self._log_nsfw: set[int] = set()

        self._logging_task.add_exception_type(asyncpg.exceptions.PostgresConnectionError)
        self._logging_task.start()

    def cog_unload(self):
        self._logging_task.stop()

    @commands.group(name="logging")
    async def logging(self, ctx: Context):
        """Logging management commands."""
        pass

    @logging.command(name="start")
    async def logging_start(self, ctx: Context):
        """Opt into logging."""
        async with ctx.db as connection:
            await OptInStatus.is_not_opted_in(connection, ctx)
            await OptInStatus.insert(connection, user_id=ctx.author.id)
            self._opted_in.add(ctx.author.id)

        await ctx.tick()

    @logging.command(name="stop")
    async def logging_stop(self, ctx: Context):
        """Opt out of logging."""
        async with ctx.db as connection:
            await OptInStatus.is_opted_in(connection, ctx)
            await OptInStatus.delete(connection, user_id=ctx.author.id)
            self._opted_in.remove(ctx.author.id)

        await ctx.tick()

    @logging.command(name="public")
    async def logging_public(self, ctx: Context, public: bool):
        """Set your logging visibility preferences."""
        async with ctx.db as connection:
            await OptInStatus.is_opted_in(connection, ctx)
            await OptInStatus.update_where(connection, "user_id = $1", ctx.author.id, public=public)

        await ctx.tick()

    @logging.command(name="nsfw")
    async def logging_nsfw(self, ctx: Context, nsfw: bool):
        """Set your NSFW channel logging preferences."""
        async with ctx.db as connection:
            await OptInStatus.is_opted_in(connection, ctx)
            await OptInStatus.update_where(connection, "user_id = $1", ctx.author.id, nsfw=nsfw)
            if nsfw:
                self._log_nsfw.add(ctx.author.id)
            else:
                with suppress(KeyError):
                    self._log_nsfw.remove(ctx.author.id)

        await ctx.tick()

    @logging.command(name="addbot", hidden=True)
    async def logging_addbot(self, ctx: Context, *, bot: discord.Member):
        """Adds a bot to logging."""
        async with ctx.db as conn:
            await OptInStatus.insert(connection=conn, user_id=bot.id, public=True, nsfw=True)
            self._opted_in.add(bot.id)

        await ctx.tick()

    @commands.command(name="vacuum_status_log")
    @commands.is_owner()
    async def vacuum_status_log(self, ctx: Context, days: int = 35):
        """Remove entries from the status log older than n days."""
        raise commands.BadArgument("This Command is not yet implemented.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.content is None:
            return

        if message.author.id not in self._opted_in:
            return

        if not isinstance(message.channel, discord.abc.GuildChannel):
            return

        if message.channel.is_nsfw() and message.author.id not in self._log_nsfw:
            return

        for i, attachment in enumerate(message.attachments):
            if attachment.content_type and TEXT_FILE_REGEX.match(attachment.content_type):

                if "charset" in attachment.content_type:
                    _, charset = attachment.content_type.rsplit("=", 1)
                else:
                    charset = "utf-8"

                try:
                    content = await attachment.read()
                    content = content.decode(charset)
                except (LookupError, UnicodeDecodeError, discord.HTTPException):
                    continue

                self.bot._message_attachment_log.append(MessageAttachmentLogEntry(message.id, i, content))

        self.bot._message_log.append(
            MessageLogEntry(
                message.channel.id,
                message.id,
                message.guild.id,
                message.author.id,
                message.content.replace('\x00', ''),
                message.channel.is_nsfw(),  # type: ignore
            )
        )
        self.bot._message_update_log.append(MessageUpdateLogEntry(message.id, discord.utils.utcnow(), message.content))

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        self.bot._message_delete_log.append(
            MessageDeleteLogEntry(
                payload.message_id,
            )
        )

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.data.get("content"):
            self.bot._message_update_log.append(
                MessageUpdateLogEntry(payload.message_id, discord.utils.utcnow(), payload.data["content"].replace('\x00', ''))
            )

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if before.status == after.status:
            changed = {a.type for a in before.activities} ^ {a.type for a in after.activities}
            if discord.ActivityType.streaming not in changed:
                return

        if before.id not in self._opted_in:
            return

        # Handle streaming edge case
        if discord.ActivityType.streaming in {a.type for a in after.activities}:
            status = Status.streaming
        else:
            status = Status.try_value(after.status.name)

        if status not in COLOURS:
            return

        if status == self.bot._last_status.get(after.id):
            return

        self.bot._status_log.append(StatusLogEntry(after.id, discord.utils.utcnow(), status))  # type: ignore
        self.bot._last_status[after.id] = status  # type: ignore

    @tasks.loop(seconds=60)
    async def _logging_task(self):
        async with MaybeAcquire(pool=self.bot.pool) as connection:
            if self.bot._status_log:
                await StatusLog.insert_many(connection, StatusLog._columns, *self.bot._status_log)
                self.bot._status_log = []

            if self.bot._message_log:
                await MessageLog.insert_many(connection, MessageLog._columns, *self.bot._message_log)
                self.bot._message_log = []

            if self.bot._message_delete_log:
                await connection.executemany(
                    f"UPDATE {MessageLog._name} SET deleted = TRUE WHERE message_id = $1",
                    self.bot._message_delete_log,
                )
                self.bot._message_delete_log = []

            if self.bot._message_attachment_log:
                await MessageAttachments.insert_many(
                    connection,
                    MessageAttachments._columns,
                    *self.bot._message_attachment_log,
                )
                self.bot._message_attachment_log = []

            if self.bot._message_update_log:
                await connection.executemany(
                    f"UPDATE {MessageLog._name} SET content = $2 WHERE message_id = $1",
                    ((entry[0], entry[2]) for entry in self.bot._message_update_log),
                )
                for entry in self.bot._message_update_log:
                    with suppress(asyncpg.exceptions.IntegrityConstraintViolationError):
                        await MessageEditHistory.insert_many(connection, MessageEditHistory._columns, entry)
                self.bot._message_update_log = []

    @_logging_task.before_loop
    async def _before_logging_task(self):
        await self.bot.wait_until_ready()

        async with MaybeAcquire(pool=self.bot.pool) as connection:

            for record in await OptInStatus.fetch(connection):
                self._opted_in.add(record["user_id"])
                if record["nsfw"]:
                    self._log_nsfw.add(record["user_id"])

            # Fill with current status data
            status_log = []
            now = discord.utils.utcnow()

            for user_id in self._opted_in:
                for guild in self.bot.guilds:
                    member = guild.get_member(user_id)
                    if member is not None:

                        # Handle streaming edge case
                        if discord.ActivityType.streaming in {a.type for a in member.activities}:
                            status = Status.streaming
                        else:
                            status = Status.try_value(member.status.name)

                        if status not in COLOURS:
                            return

                        status_log.append(StatusLogEntry(user_id, now, status))  # type: ignore
                        self.bot._last_status[member.id] = status  # type: ignore
                        break

            await StatusLog.insert_many(connection, StatusLog._columns, *status_log)


def setup(bot: LoggingBot):
    if not hasattr(bot, "_logging"):
        bot._logging = True
        bot._message_log = []
        bot._message_delete_log = []
        bot._message_attachment_log = []
        bot._message_update_log = []
        bot._status_log = []
        bot._last_status = {}
    bot.add_cog(Logging(bot))
