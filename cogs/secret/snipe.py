from typing import Optional
import discord
from discord import utils
from discord.ext import commands

from bot import BotBase, Context

from cogs.logging.logging import Message_Log
from utils.tools import format_dt


class Snipe(commands.Cog, command_attrs=dict(hidden=True)):

    def __init__(self, bot: BotBase):
        self.bot = bot

    async def cog_check(self, ctx: Context):
        return await commands.is_owner().predicate(ctx)

    @commands.command()
    async def history(self, ctx: Context, a: Optional[discord.TextChannel] = None, b: Optional[discord.User] = None, c: int = 20):
        channel, user, limit = a, b, c
        if channel is None and user is None:
            raise commands.BadArgument('Invalid args')

        if channel is None:
            records = await Message_Log.fetch(user_id=user.id, order_by='message_id DESC', limit=limit)
        elif user is None:
            records = await Message_Log.fetch(channel_id=channel.id, order_by='message_id DESC', limit=limit)
        else:
            records = await Message_Log.fetch(channel_id=channel.id, user_id=user.id, order_by='message_id DESC', limit=limit)

        if not records:
            raise commands.BadArgument('No data')

        data = ''
        for _, message_id, _, user_id, content, _ in records:
            created_at = utils.snowflake_time(message_id)
            data += f'<@{user_id}> @ {format_dt(created_at)}: {content}\n\n'
        await ctx.send(data)


def setup(bot: BotBase):
    bot.add_cog(Snipe(bot))
