import discord
from discord.ext import commands, menus

from donphan import Column, SQLType, Table, MaybeAcquire

from ditto import Cog, Context
from ditto.utils.paginator import EmbedPaginator

from bot import BotBase


class Voice_Woes_Whitelist(Table):
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

    @commands.group(aliases=["vww"])
    @commands.check_any(commands.is_owner(), is_dpy_mod())
    async def voice_woes_whitelist(self, ctx: Context):
        """Voice woes whitelist management commands."""
        if ctx.invoked_subcommand is not None:
            return

        paginator = EmbedPaginator(
            colour=discord.Colour.orange(),
            title="Voice Woes Whitelist",
            max_description=512,
        )
        paginator.set_footer(text="user (bb)vww add, and (bb)vww remove to manage the whitelist.")

        for user_id in self.bot.whitelisted_users:
            paginator.add_line(f"<@{user_id}>")

        menu = menus.MenuPages(paginator)
        await menu.start(ctx)

    @voice_woes_whitelist.command(name="add")
    async def voice_woes_whiitelist_add(self, ctx: Context, member: discord.User):
        """Add a user to the voice woes whitelist."""
        async with ctx.db as connection:
            await Voice_Woes_Whitelist.insert(connection, user_id=member.id)
        self.bot.whitelisted_users.add(member.id)
        await ctx.tick()

    @voice_woes_whitelist.command(name="remove")
    async def voice_woes_whiitelist_remove(self, ctx: Context, member: discord.User):
        """Remove a user from the voice woes whitelist."""
        async with ctx.db as connection:
            await Voice_Woes_Whitelist.delete(connection, user_id=member.id)
        self.bot.whitelisted_users.remove(member.id)
        await ctx.tick()

    async def add_users(self):
        await self.bot.wait_until_ready()

        async with MaybeAcquire(pool=self.bot.pool) as connection:
            for record in await Voice_Woes_Whitelist.fetch(connection):
                self.bot.whitelisted_users.add(record["user_id"])


def setup(bot: BotBase):
    bot.add_cog(Whitelist(bot))
