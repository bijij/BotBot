import datetime
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from contextlib import suppress
from typing import Set

import asyncpg
from donphan import Column, enum, MaybeAcquire, Table, SQLType

import discord
from discord.ext import commands, tasks

from bot import BotBase, Context


COLOURS = {
    None: (0, 0, 0, 0),
    discord.Status.online: (67, 181, 129, 255),
    discord.Status.offline: (116, 127, 141, 255),
    discord.Status.idle: (250, 166, 26, 255),
    discord.Status.dnd: (240, 71, 71, 255)
}


class Message_Log(Table, schema='logging'):  # type: ignore
    channel_id: SQLType.BigInt = Column(primary_key=True)
    message_id: SQLType.BigInt = Column(primary_key=True)
    guild_id: SQLType.BigInt = Column(index=True)
    user_id: SQLType.BigInt = Column(index=True)
    content: str
    nsfw: bool = Column(default=False)

    @classmethod
    async def get_user_log(cls, user: discord.User, nsfw: bool = False, *, connection: asyncpg.Connection = None) -> str:
        async with MaybeAcquire(connection=connection) as connection:
            data, = await connection.fetchrow(f'SELECT string_agg(content, \'\n\') FROM {cls._name}\
            WHERE user_id = $1 AND nsfw <= $2', user.id, nsfw)
        return data

    @classmethod
    async def get_guild_log(cls, guild: discord.Guild, nsfw: bool = False, *, connection: asyncpg.Connection = None) -> str:
        async with MaybeAcquire(connection=connection) as connection:
            data, = await connection.fetchrow(f'SELECT string_agg(content, \'\n\') FROM {cls._name} \
            WHERE guild_id = $1 and nsfw <= $2', guild.id, nsfw)
        return data


Status = enum('Status', 'online offline idle dnd', schema='logging')


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

    @commands.group(name='timezone')
    async def timezone(self, ctx):
        """Timezone management commands."""
        pass

    @timezone.command(name='set')
    async def timezone_set(self, ctx, timezone: zoneinfo.ZoneInfo):
        """Set your timezone."""
        await Timezones.insert(update_on_conflict=Timezones.timezone, user_id=ctx.author.id, timezone=timezone.key)
        await ctx.tick()

    @timezone.command(name='delete', aliases=['unset'])
    async def timezone_delete(self, ctx):
        """Removes your timezone from the database"""
        await Timezones.delete(user_id=ctx.author.id)
        await ctx.tick()

    @commands.command(name='vaccum_status_log')
    @commands.is_owner()
    async def vaccum_status_log(self, ctx: Context, days: int = 35):
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

        self.bot._message_log.append((message.channel.id, message.id, message.guild.id, message.author.id, message.content, message.channel.is_nsfw()))

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
    async def _logging_task(self):
        async with MaybeAcquire() as conn:
            if self.bot._status_log:
                await Status_Log.insert_many(Status_Log._columns, *self.bot._status_log, connection=conn)
                self.bot._status_log = list()

            if self.bot._message_log:
                await Message_Log.insert_many(Message_Log._columns, *self.bot._message_log, connection=conn)
                self.bot._message_log = list()

    @_logging_task.before_loop
    async def _before_logging_task(self):
        await self.bot.wait_until_ready()

        for record in await Opt_In_Status.fetchall():
            self._opted_in.add(record['user_id'])
            if record['nsfw']:
                self._log_nsfw.add(record['user_id'])


def setup(bot: BotBase):
    if not hasattr(bot, '_logging'):
        bot._logging = True
        bot._message_log = list()
        bot._status_log = list()
        bot._last_status = dict()
    bot.add_cog(Logging(bot))
