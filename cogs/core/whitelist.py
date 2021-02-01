import asyncio

import discord
from discord.ext import commands

from donphan import Column, SQLType, Table

from bot import BotBase, Context

class Voice_Woes_Whitelist(Table):
    user_id: SQLType.BigInt = Column(primary_key=True)


DPY_ID = 336642139381301249
DPY_MOD_ID = 381978546123440130


def is_dpy_mod():

    async def predicate(ctx):
        dpy = ctx.bot.get_guild(336642139381301249)
        if dpy is None:
            raise commands.CheckFailure('Could not find dpy')
        
        member = dpy.get_member(ctx.author.id)
        if member is None:
            raise commands.CheckFailure('You are not in the discord.py server.')

        mod_role = dpy.get_role(DPY_MOD_ID)
        if mod_role is None:
            raise commands.CheckFailure('Fuck')

        if mod_role not in member.roles:
            raise commands.CheckFailure('You must be a discord.py server moderator to use this command.')

        return True

    return commands.check(predicate)



class Whitelist(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot
        asyncio.create_task(self.add_users())

    @commands.group(aliases=['vww'])
    @commands.check_any(commands.is_owner, is_dpy_mod)
    async def voice_woes_whitelist(self, ctx):
        """Voice woes whitelist management commands."""
        ...

    @voice_woes_whitelist.command(name='add')
    async def voice_woes_whiitelist_add(self, ctx: Context, member: discord.User):
        """Add a user to the voice woes whitelist."""
        await Voice_Woes_Whitelist.insert(user_id=member.id)
        self.bot.whitelisted_users.add(member.id)
        await ctx.tick()

    @voice_woes_whitelist.command(name='remove')
    async def voice_woes_whiitelist_remove(self, ctx: Context, member: discord.User):
        """Remove a user from the voice woes whitelist."""
        await Voice_Woes_Whitelist.delete_where('user_id=$1', member.id)
        self.bot.whitelisted_users.remove(member.id)
        await ctx.tick()

    async def add_users(self):
        for record in await Voice_Woes_Whitelist.fetchall():
            self.bot.whitelisted_users.add(record['user_id'])
