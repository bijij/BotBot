from typing import Union

import discord
from discord.ext import commands

from bot import BotBase, Context


class ModerationTools(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

    @commands.command(aliases=['hackban'])
    @commands.check(commands.bot_has_guild_permissions(ban_members=True))
    @commands.check_any(commands.has_guild_permissions(ban_members=True), commands.is_owner())
    async def ban(self, ctx: Context, user: Union[discord.Member, discord.User], *, reason: str = None):
        """Bans a member from the server.

        `user`: the user to ban.
        `reason`: the reason for the ban.
        """
        await ctx.guild.ban(user, reason=reason)
        await ctx.send(f'Banned {user} from the server.', delete_after=5)

    @commands.command()
    @commands.check(commands.bot_has_guild_permissions(ban_members=True))
    @commands.check_any(commands.has_guild_permissions(ban_members=True), commands.is_owner())
    async def unban(self, ctx: Context, user: discord.User, *, reason: str = None):
        """Unbans a member from the server.

        `user`: the user to unban.
        `reason`: the reason for the unban.
        """
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f'{user} was unbanned from the server.', delete_after=5)

    @commands.command()
    @commands.check(commands.bot_has_guild_permissions(kick_members=True))
    @commands.check_any(commands.has_guild_permissions(kick_members=True), commands.is_owner())
    async def kick(self, ctx: Context, user: discord.Member, *, reason: str = None):
        """Kicks a member from the server.

        `user`: the user to kick.
        `reason`: the reason for the kick.
        """
        await user.kick(reason=reason)
        await ctx.send(f'Kicked {user} from the server.', delete_after=5)

    @commands.command()
    @commands.check_any(commands.has_guild_permissions(manage_messages=True), commands.is_owner())
    async def cleanup(self, ctx: Context, limit: int = 50):
        """Deletes messages related to bot commands from the channel.

        `limit`: the number of messages to process, can be a maximum of 100 messages.
        """
        to_delete = []

        if not 0 < limit <= 100:
            raise commands.BadArgument('You can only delete between 1 and 100 messages.')

        async for message in ctx.channel.history(limit=limit):

            context = await self.bot.get_context(message)
            if message.author == self.bot.user:
                to_delete.append(message)

            if ctx.channel.permissions_for(ctx.me).manage_messages and context.command is not None:
                to_delete.append(message)

        await ctx.send(f'Deleted {len(to_delete)} messages', delete_after=5)

        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.channel.delete_messages(to_delete)
        else:
            for message in to_delete:
                await message.delete(silent=True)

    @commands.command()
    @commands.check(commands.bot_has_guild_permissions(manage_messages=True))
    @commands.check_any(commands.has_guild_permissions(manage_messages=True), commands.is_owner())
    async def nuke(self, ctx: Context, limit: int = 50, *, user: Union[discord.Member, discord.User] = None):
        """Deletes up to a given number of messages from the channel.

        `limit`: the number of messages to process, can be a maximum of 100 messages.
        `user`: Allows for only messages from a given user to be deleted.
        """
        if not 0 < limit <= 100:
            raise commands.BadArgument('You can only delete between 1 and 100 messages.')

        def check(message: discord.Message):
            return user is None or message.author == user

        deleted = await ctx.channel.purge(limit=limit, check=check)

        await ctx.send(f'Deleted {len(deleted)} messages', delete_after=5)


def setup(bot: BotBase):
    bot.add_cog(ModerationTools(bot))
