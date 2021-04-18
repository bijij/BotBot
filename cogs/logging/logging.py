import datetime
import re

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from contextlib import suppress
from typing import List, Set

import asyncpg
from donphan import Column, enum, MaybeAcquire, Table, SQLType

import discord
from discord.ext import commands, tasks

from bot import BotBase, Context

TEXT_FILE_REGEX = re.compile(r'^.*; charset=.*$')


COLOURS = {
    None: (0, 0, 0, 0),
    'online': (67, 181, 129, 255),
    'offline': (116, 127, 141, 255),
    'idle': (250, 166, 26, 255),
    'dnd': (240, 71, 71, 255),
    'streaming': (84, 51, 141, 255),
}


class Message_Log(Table, schema='logging'):  # type: ignore
    channel_id: SQLType.BigInt = Column(primary_key=True)
    message_id: SQLType.BigInt = Column(primary_key=True)
    guild_id: SQLType.BigInt = Column(index=True)
    user_id: SQLType.BigInt = Column(index=True)
    content: str
    nsfw: bool = Column(default=False)
    deleted: bool = Column(default=False)

    @classmethod
    async def get_user_log(cls, user: discord.User, nsfw: bool = False, flatten_case: bool = False, *, connection: asyncpg.Connection = None) -> List[str]:
        async with MaybeAcquire(connection) as connection:
            query = f"""(SELECT message_id, content from {Message_Log._name} WHERE deleted = false AND user_id = $1 AND nsfw <= $2 AND content LIKE '% %') _
            UNION
            SELECT message_id, content from {Message_Attachments._name} INNER JOIN _ on (message_id = _.message_id)
            """
            data = await connection.fetch(query, user.id, nsfw)
        return [record['content'].lower() if flatten_case else record['content'] for record in data]

    @classmethod
    async def get_guild_log(cls, guild: discord.Guild, nsfw: bool = False, flatten_case: bool = False, *, connection: asyncpg.Connection = None) -> List[str]:
        async with MaybeAcquire(connection) as connection:
            query = f"""(SELECT message_id, content FROM {Message_Log._name} WHERE deleted = false AND guild_id = $1 AND nsfw <= $2 AND content LIKE '% %') _
            UNION
            SELECT message_id, content FROM {Message_Attachments._name} INNER JOIN _ on (message_id = _.message_id)
            """
            data = await connection.fetch(query, guild.id, nsfw)
        return [record['content'].lower() if flatten_case else record['content'] for record in data]


class Message_Attachments(Table, schema='logging'): # type: ignore
    message_id: SQLType.BigInt = Column(primary_key=True, references=Message_Log.message_id)
    attachment_id: SQLType.BigInt
    content: str


class Message_Edit_History(Table, schema='logging'):  # type: ignore
    message_id: SQLType.BigInt = Column(primary_key=True, references=Message_Log.message_id)
    created_at: datetime.datetime = Column(primary_key=True)
    content: str


Status = enum('Status', 'online offline idle dnd streaming', schema='logging')


class Status_Log(Table, schema='logging'):  # type: ignore
    user_id: SQLType.BigInt = Column(primary_key=True, index=True)
    timestamp: datetime.datetime = Column(primary_key=True)
    status: Status  # type: ignore


class Timezones(Table, schema='logging'):  # type: ignore
    user_id: SQLType.BigInt = Column(primary_key=True, index=True)
    timezone: str = Column(nullable=False)


class Opt_In_Status(Table, schema='logging'):  # type: ignore
    user_id: SQLType.BigInt = Column(primary_key=True, index=True)
    public: bool = Column(default=False)
    nsfw: bool = Column(default=False)

    @classmethod
    async def is_opted_in(cls, ctx: Context, *, connection: asyncpg.Connection = None):
        opt_in_status = await cls.fetchrow(connection=connection, user_id=ctx.author.id)
        if opt_in_status is None:
            raise commands.BadArgument(f'You have not opted in to logging. You can do so with `{ctx.bot.prefix}logging start`')

    @classmethod
    async def is_not_opted_in(cls, ctx: Context, *, connection: asyncpg.Connection = None):
        opt_in_status = await cls.fetchrow(connection=connection, user_id=ctx.author.id)
        if opt_in_status is not None:
            raise commands.BadArgument('You have already opted into logging.')

    @classmethod
    async def is_public(cls, ctx: Context, user: discord.User, *, connection: asyncpg.Connection = None):
        opt_in_status = await cls.fetchrow(connection=connection, user_id=user.id)
        if opt_in_status is None:
            if user == ctx.author:
                raise commands.BadArgument(f'You have not opted in to logging. You can do so with `{ctx.bot.prefix}logging start`')
            else:
                raise commands.BadArgument(f'User "{user}" has not opted in to logging.')

        if user != ctx.author and not opt_in_status['public']:
            raise commands.BadArgument(f'User "{user}" has not made their logs public.')


class Logging(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

        self._opted_in: Set[int] = set()
        self._log_nsfw: Set[int] = set()

        self._logging_task.add_exception_type(asyncpg.PostgresConnectionError)
        self._logging_task.start()

    def cog_unload(self):
        self._logging_task.stop()

    @commands.group(name='logging')
    async def logging(self, ctx: Context):
        """Logging management commands."""
        pass

    @logging.command(name='start')
    async def logging_start(self, ctx: Context):
        """Opt into logging."""
        async with ctx.db as conn:
            await Opt_In_Status.is_not_opted_in(ctx, connection=conn)
            await Opt_In_Status.insert(connection=conn, user_id=ctx.author.id)
            self._opted_in.add(ctx.author.id)

        await ctx.tick()

    @logging.command(name='stop')
    async def logging_stop(self, ctx: Context):
        """Opt out of logging."""
        async with ctx.db as conn:
            await Opt_In_Status.is_opted_in(ctx, connection=conn)
            await Opt_In_Status.delete(connection=conn, user_id=ctx.author.id)
            self._opted_in.remove(ctx.author.id)

        await ctx.tick()

    @logging.command(name='public')
    async def logging_public(self, ctx: Context, public: bool):
        """Set your logging visibility preferences."""
        async with ctx.db as conn:
            await Opt_In_Status.is_opted_in(ctx, connection=conn)
            await Opt_In_Status.update_where("user_id = $1", ctx.author.id, connection=conn, public=public)

        await ctx.tick()

    @logging.command(name='nsfw')
    async def logging_nsfw(self, ctx: Context, nsfw: bool):
        """Set your NSFW channel logging preferences."""
        async with ctx.db as conn:
            await Opt_In_Status.is_opted_in(ctx, connection=conn)
            await Opt_In_Status.update_where("user_id = $1", ctx.author.id, connection=conn, nsfw=nsfw)
            if nsfw:
                self._log_nsfw.add(ctx.author.id)
            else:
                with suppress(KeyError):
                    self._log_nsfw.remove(ctx.author.id)

        await ctx.tick()

    @logging.command(name='addbot', hidden=True)
    async def logging_addbot(self, ctx: Context, *, bot: discord.Member):
        """Adds a bot to logging."""
        async with ctx.db as conn:
            await Opt_In_Status.insert(connection=conn, user_id=bot.id, public=True, nsfw=True)
            self._opted_in.add(bot.id)

        await ctx.tick()

    @commands.group(name='timezone', aliases=['tz'])
    async def timezone(self, ctx):
        """Timezone management commands."""
        pass

    @timezone.command(name='set')
    async def timezone_set(self, ctx, *, timezone: zoneinfo.ZoneInfo):
        """Set your timezone."""
        await Timezones.insert(update_on_conflict=Timezones.timezone, user_id=ctx.author.id, timezone=timezone.key)
        await ctx.tick()

    @timezone.command(name='get')
    async def timezone_get(self, ctx, *, user: discord.User = None):
        """Get a user's timezone.

        `user`: The user who's timezone to display, defaults to you.
        """
        user = user or ctx.author

        async with ctx.db as conn:
            await Opt_In_Status.is_public(ctx, user, connection=conn)
            record = await Timezones.fetchrow(connection=conn, user_id=user.id)

        if record is None:
            raise commands.BadArgument(f"User {user.name} doesn't have a saved timezone.")

        timezone = zoneinfo.ZoneInfo(record['timezone'])
        delta = timezone.utcoffset(discord.utils.utcnow())
        seconds = int(delta.total_seconds())

        utc_offset = f"UTC{seconds // 3600:+03}:{abs(seconds) // 60 % 60:02}"

        await ctx.send(embed=discord.Embed(
            title="Timezone info",
            description=f"User {user.name}'s timezone is {timezone} ({utc_offset})",
            colour=discord.Colour.blue()
        ))

        await ctx.tick()

    @timezone.command(name='delete', aliases=['unset'])
    async def timezone_delete(self, ctx):
        """Removes your timezone from the database"""
        await Timezones.delete(user_id=ctx.author.id)
        await ctx.tick()

    @commands.command(name='vacuum_status_log')
    @commands.is_owner()
    async def vacuum_status_log(self, ctx: Context, days: int = 35):
        """Remove entries from the status log older than n days."""
        raise commands.BadArgument('This Command is not yet implemented.')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.content is None:
            return

        if message.author.id not in self._opted_in:
            return

        if message.guild is None:
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
                
                self.bot._message_attachment_log.append((message.id, i, content))
                
        self.bot._message_log.append((message.channel.id, message.id, message.guild.id, message.author.id, message.content, message.channel.is_nsfw(), False))
        self.bot._message_update_log.append((message.id, discord.utils.utcnow(), message.content))

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        self.bot._message_delete_log.append((payload.message_id,))

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.data.get('content'):
            self.bot._message_update_log.append((payload.message_id, discord.utils.utcnow(), payload.data['content']))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.status == after.status:
            changed = {a.type for a in before.activities} ^ {a.type for a in after.activities}
            if discord.ActivityType.streaming not in changed:
                return

        if before.id not in self._opted_in:
            return

        # Handle streaming edge case
        if discord.ActivityType.streaming in {a.type for a in after.activities}:
            status = 'streaming'
        else:
            status = after.status.name

        if status not in COLOURS:
            return

        if status == self.bot._last_status.get(after.id):
            return

        self.bot._status_log.append((after.id, discord.utils.utcnow(), status))
        self.bot._last_status[after.id] = status

    @tasks.loop(seconds=60)
    async def _logging_task(self):
        async with MaybeAcquire() as conn:
            if self.bot._status_log:
                await Status_Log.insert_many(Status_Log._columns, *self.bot._status_log, connection=conn)
                self.bot._status_log = []

            if self.bot._message_log:
                await Message_Log.insert_many(Message_Log._columns, *self.bot._message_log, connection=conn)
                self.bot._message_log = []

            if self.bot._message_delete_log:
                await conn.executemany(f"UPDATE {Message_Log._name} SET deleted = TRUE WHERE message_id = $1", self.bot._message_delete_log)
                self.bot._message_delete_log = []

            if self.bot._message_attachment_log:
                await Message_Attachments.insert_many(Message_Attachments._columns, *self.bot._message_attachment_log, connection=conn)
                self.bot._message_attachment_log = []

            if self.bot._message_update_log:
                await conn.executemany(f"UPDATE {Message_Log._name} SET content = $2 WHERE message_id = $1", ((entry[0], entry[2]) for entry in self.bot._message_update_log))
                for entry in self.bot._message_update_log:
                    with suppress(asyncpg.exceptions.IntegrityConstraintViolationError):
                        await Message_Edit_History.insert_many(Message_Edit_History._columns, entry, connection=conn)
                self.bot._message_update_log = []

    @_logging_task.before_loop
    async def _before_logging_task(self):
        await self.bot.wait_until_ready()

        for record in await Opt_In_Status.fetchall():
            self._opted_in.add(record['user_id'])
            if record['nsfw']:
                self._log_nsfw.add(record['user_id'])

        # Fill with current status data
        status_log = []
        now = discord.utils.utcnow()

        for user_id in self._opted_in:
            for guild in self.bot.guilds:
                member = guild.get_member(user_id)
                if member is not None:

                    # Handle streaming edge case
                    if discord.ActivityType.streaming in {a.type for a in member.activities}:
                        status = 'streaming'
                    else:
                        status = member.status.name

                    if status not in COLOURS:
                        return

                    status_log.append((user_id, now, status))
                    self.bot._last_status[member.id] = status
                    break

        await Status_Log.insert_many(Status_Log._columns, *status_log)


def setup(bot: BotBase):
    if not hasattr(bot, '_logging'):
        bot._logging = True
        bot._message_log = []
        bot._message_delete_log = []
        bot._message_attachment_log = []
        bot._message_update_log = []
        bot._status_log = []
        bot._last_status = {}
    bot.add_cog(Logging(bot))
