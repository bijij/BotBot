import datetime

from typing import Set

import asyncpg

import discord
from discord.ext import commands, tasks

from bot import BotBase, Context, ConnectionContext


COLOURS = {
    None: (0, 0, 0, 0),
    discord.Status.online: (67, 181, 129, 255),
    discord.Status.offline: (116, 127, 141, 255),
    discord.Status.idle: (250, 166, 26, 255),
    discord.Status.dnd: (240, 71, 71, 255)
}


async def is_opted_in(ctx: Context, conn: asyncpg.Connection):
    opt_in_status = await conn.fetchrow('SELECT * FROM logging.opt_in_status WHERE user_id = $1', ctx.author.id)
    if opt_in_status is None:
        raise commands.BadArgument(f'You have not opted in to logging. You can do so with `{ctx.bot.prefix}logging start`')


async def is_not_opted_in(ctx: Context, conn: asyncpg.Connection):
    opt_in_status = await conn.fetchrow('SELECT * FROM logging.opt_in_status WHERE user_id = $1', ctx.author.id)
    if opt_in_status is not None:
        raise commands.BadArgument('You have already opted into logging.')


async def is_public(ctx: Context, user: discord.User, conn: asyncpg.Connection):
    opt_in_status = await conn.fetchrow('SELECT * FROM logging.opt_in_status WHERE user_id = $1', user.id)
    if opt_in_status is None:
        raise commands.BadArgument(f'User "{user}" has not opted in to logging.')

    if user != ctx.author and not opt_in_status['public']:
        raise commands.BadArgument(f'User "{user}" has not made their logs public.')


class Logging(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

        self._opted_in: Set[int] = set()

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
        """Set your logging visibility preferences."""
        async with ctx.db as conn:
            await is_opted_in(ctx, conn)
            await conn.execute('UPDATE logging.opt_in_status SET public = $2 WHERE user_id = $1', ctx.author.id, public)

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

        if message.channel.is_nsfw():
            return

        self.bot._message_log.append((message.channel.id, message.id, message.guild.id, message.author.id, message.content))

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
        async with ConnectionContext(pool=self.bot.pool) as conn:
            if self.bot._status_log:
                await conn.executemany('INSERT INTO logging.status_log VALUES ($1, $2, $3)', self.bot._status_log)
                self.bot._status_log = list()

            if self.bot._message_log:
                await conn.executemany('INSERT INTO logging.message_log VALUES ($1, $2, $3, $4, $5)', self.bot._message_log)
                self.bot._message_log = list()

    @_logging_task.before_loop
    async def _before_logging_task(self):
        await self.bot.wait_until_ready()

        async with ConnectionContext(pool=self.bot.pool) as conn:
            records = await conn.fetch('SELECT * FROM logging.opt_in_status')

        for record in records:
            self._opted_in.add(record['user_id'])


def setup(bot: BotBase):
    if not hasattr(bot, '_logging'):
        bot._logging = True
        bot._message_log = list()
        bot._status_log = list()
        bot._last_status = dict()
    bot.add_cog(Logging(bot))
