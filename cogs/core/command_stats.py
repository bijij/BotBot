import asyncio

from collections import Counter, namedtuple
from typing import Any

import asyncpg
from donphan import Column, SQLType, Table

import discord
from discord.ext import commands, tasks

from ditto import BotBase, Cog, Context


class Commands(Table, schema="core"):
    message_id: SQLType.BigInt = Column(primary_key=True)
    guild_id: SQLType.BigInt = Column(index=True)
    channel_id: SQLType.BigInt
    user_id: SQLType.BigInt = Column(index=True)
    invoked_at: SQLType.Timestamp
    prefix: str
    command: str
    failed: bool


CommandInvoke = namedtuple(
    "CommandInvoke",
    (
        "message_id",
        "guild_id",
        "channel_id",
        "user_id",
        "invoked_at",
        "prefix",
        "command",
        "failed",
    ),
)


class CommandStats(Cog):
    def __init__(self, bot: BotBase):
        self.bot = bot

        self._batch_lock = asyncio.Lock()
        self._batch_data = []  # type: ignore

        self.bulk_insert.add_exception_type(asyncpg.exceptions.PostgresConnectionError)
        self.bulk_insert.start()

    def cog_unload(self):
        self.bulk_insert.stop()

    async def cog_check(self, ctx: Context):
        return await commands.is_owner().predicate(ctx)

    @commands.group(name="command", invoke_without_command=True, hidden=True)
    async def command(self, ctx: Context):
        """Comamnd usage statistics commands."""
        pass

    @command.command(name="stats")
    async def command_stats(self, ctx: Context):
        """Displays basic information about command usage."""
        total_occurunces = sum(self.bot._command_stats.values())
        total_per_min = total_occurunces / (self.bot.uptime / 60)

        embed = discord.Embed(
            colour=ctx.me.colour,
            description=f"Recieved {total_occurunces} command invokes. ({total_per_min:.2f}/min)",
        ).set_author(
            name=f"{self.bot.user.name} command usage stats:",
            icon_url=self.bot.user.avatar.url,
        )

        for command, occurunces in self.bot._command_stats.most_common(5):
            per_minute = occurunces / (self.bot.uptime / 60)
            embed.add_field(
                name=f"`{command}`",
                value=f"{occurunces} ({per_minute:.2f}/min)",
                inline=False,
            )

        await ctx.send(embed=embed)

    @command.group(name="history", invoke_without_command=True)
    async def command_history(self, ctx: Context):
        """Returns information on the 10 most recently used commands."""
        records = await Commands.fetch(order_by="invoked_at DESC", limit=10)

        embed = (
            discord.Embed(colour=ctx.me.colour)
            .set_author(
                name=f"{self.bot.user.name} command history:",
                icon_url=self.bot.user.avatar.url,
            )
            .set_footer(text="commands marked with a [!] failed.")
        )

        for (
            message_id,
            _,
            channel_id,
            user_id,
            invoked_at,
            prefix,
            command,
            failed,
        ) in records:
            embed.add_field(
                name=f"`{prefix}{command}` @ {invoked_at}",
                value=f'{"[!]" if failed else ""} <@!{user_id}> in <#{channel_id}>',
                inline=False,
            )

        await ctx.send(embed=embed)

    @commands.group(name="socket", invoke_without_command=True, hidden=True)
    async def socket(self, ctx: Context):
        """Websocket event statistics commands."""
        pass

    @socket.command(name="stats")
    async def socket_stats(self, ctx: Context):
        """Displays basic information about socket statistics."""
        total_occurunces = sum(self.bot._socket_stats.values())
        total_per_min = total_occurunces / (self.bot.uptime / 60)

        embed = discord.Embed(
            colour=ctx.me.colour,
            description=f"Observed {total_occurunces} socket events. ({total_per_min:.2f}/min)",
        ).set_author(
            name=f"{self.bot.user.name} socket event stats:",
            icon_url=self.bot.user.avatar.url,
        )

        for event, occurunces in self.bot._socket_stats.most_common(25):
            per_minute = occurunces / (self.bot.uptime / 60)
            embed.add_field(
                name=f"`{event}`",
                value=f"{occurunces} ({per_minute:.2f}/min)",
                inline=True,
            )

        await ctx.send(embed=embed)

    # region event recording

    async def _record_command(self, ctx: Context):
        command = ctx.command

        if command is None:
            return

        guild_id = ctx.guild.id if ctx.guild is not None else None

        self.bot._command_stats[command.qualified_name] += 1

        invoke = CommandInvoke(
            message_id=ctx.message.id,
            guild_id=guild_id,
            channel_id=ctx.channel.id,
            user_id=ctx.author.id,
            invoked_at=ctx.message.created_at,
            prefix=ctx.prefix,
            command=command.qualified_name,
            failed=ctx.command_failed,
        )

        async with self._batch_lock:
            self._batch_data.append(invoke)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: Context):
        await self._record_command(ctx)

    @commands.Cog.listener()
    async def on_command_error(self, ctx: Context, error: Exception):
        await self._record_command(ctx)

    @commands.Cog.listener()
    async def on_socket_response(self, msg: dict[Any, Any]):
        self.bot._socket_stats[msg.get("t")] += 1

    @tasks.loop(seconds=10)
    async def bulk_insert(self):
        async with self._batch_lock:
            if self._batch_data:
                await Commands.insert_many(Commands._columns, *self._batch_data)
                self._batch_data.clear()

    # endregion


def setup(bot: BotBase):
    if not hasattr(bot, "_command_stats"):
        bot._command_stats = Counter()
    if not hasattr(bot, "_socket_stats"):
        bot._socket_stats = Counter()
    bot.add_cog(Stats(bot))
