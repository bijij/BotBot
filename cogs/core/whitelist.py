from typing import Optional
import discord
from discord.ext import commands, menus
from ditto.config import CONFIG

from donphan import Column, SQLType, Table, MaybeAcquire

from ditto import Cog, Context
from ditto.utils.paginator import EmbedPaginator

from bot import BotBase


class ChannelWhitelist(Table):
    channel_id: Column[SQLType.BigInt] = Column(primary_key=True)
    user_id: Column[SQLType.BigInt] = Column(primary_key=True)


DPY_ID = 336642139381301249
DPY_MOD_ID = 381978546123440130


def is_dpy_mod():
    async def predicate(ctx):
        dpy = ctx.bot.get_guild(336642139381301249)
        if dpy is None:
            raise commands.CheckFailure("Could not find dpy")

        member = dpy.get_member(ctx.author.id)
        if member is None:
            raise commands.CheckFailure("You are not in the discord.py server.")

        mod_role = dpy.get_role(DPY_MOD_ID)
        if mod_role is None:
            raise commands.CheckFailure("Fuck")

        if mod_role not in member.roles:
            raise commands.CheckFailure("You must be a discord.py server moderator to use this command.")

        return True

    return commands.check(predicate)


class Whitelist(Cog):
    def __init__(self, bot: BotBase):
        self.bot = bot
        bot.loop.create_task(self.add_users())

    @commands.group()
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), is_dpy_mod())
    async def whitelist(self, ctx: Context, *, channel: Optional[discord.TextChannel] = None):
        """Channel whitelist commands."""
        channel = channel or ctx.channel

        if channel.id not in self.bot.whitelisted_users:
            raise commands.BadArgument('This channel does not have a whitelist.')

        if ctx.invoked_subcommand is not None:
            return

        paginator = EmbedPaginator(
            colour=discord.Colour.orange(),
            title="Channel Whitelist",
            max_description=512,
        )
        paginator.set_footer(text="use (bb)whitelist add, and (bb)whitelist remove to manage the whitelist.")

        for user_id in self.bot.whitelisted_users[channel.id]:
            paginator.add_line(f"<@{user_id}>")

        menu = menus.MenuPages(paginator)
        await menu.start(ctx)

    @whitelist.command(name="add")
    async def whitelist_add(
        self, ctx: Context, member: discord.User, *, channel: Optional[discord.TextChannel] = None
    ):
        """Add a user to the channel whitelist"""
        channel = channel or ctx.channel
        async with ctx.db as connection:
            await ChannelWhitelist.insert(connection, channel_id=channel.id, user_id=member.id)

        if channel.id not in self.bot.whitelisted_users:
            self.bot.whitelisted_users[channel.id] = set()

        self.bot.whitelisted_users[channel.id].add(member.id)
        await ctx.tick()

    @whitelist.command(name="remove")
    async def whitelist_remove(
        self, ctx: Context, member: discord.User, *, channel: Optional[discord.TextChannel] = None
    ):
        """Remove a user from the channel whitelist"""
        channel = channel or ctx.channel
        async with ctx.db as connection:
            await ChannelWhitelist.delete(connection, channel_id=channel.id, user_id=member.id)
        self.bot.whitelisted_users[channel.id].remove(member.id)
        await ctx.tick()

    @commands.group(aliases=["vww"])
    @commands.guild_only()
    @commands.check_any(commands.is_owner(), is_dpy_mod())
    async def voice_woes_whitelist(self, ctx: Context):
        """Voice woes whitelist management commands."""
        await ctx.invoke(self.whitelist, channel=CONFIG.DPY_VOICE_GENERAL)

    @voice_woes_whitelist.command(name="add")
    async def voice_woes_whitelist_add(self, ctx: Context, member: discord.User):
        """Add a user to the voice woes whitelist."""
        await ctx.invoke(self.whitelist_add, member, channel=CONFIG.DPY_VOICE_GENERAL)

    @voice_woes_whitelist.command(name="remove")
    async def voice_woes_whitelist_remove(self, ctx: Context, member: discord.User):
        """Remove a user from the voice woes whitelist."""
        await ctx.invoke(self.whitelist_remove, member, channel=CONFIG.DPY_VOICE_GENERAL)

    async def add_users(self):
        await self.bot.wait_until_ready()

        async with MaybeAcquire(pool=self.bot.pool) as connection:
            for record in await ChannelWhitelist.fetch(connection):
                if record["channel_id"] not in self.bot.whitelisted_users:
                    self.bot.whitelisted_users[record["channel_id"]] = set()
                self.bot.whitelisted_users[record["channel_id"]].add(record["user_id"])


def setup(bot: BotBase):
    bot.add_cog(Whitelist(bot))
