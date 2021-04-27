from typing import Optional
import discord
from discord import utils
from discord.ext import commands

from bot import BotBase, Context

from cogs.logging.db import Message_Log
from ditto.utils.time import human_friendly_timestamp


class Snipe(commands.Cog, command_attrs=dict(hidden=True)):  # type: ignore[call-arg]
    def __init__(self, bot: BotBase):
        self.bot = bot

    async def cog_check(self, ctx: Context):
        return await commands.is_owner().predicate(ctx)

    @commands.command()
    async def history(
        self, ctx: Context, a: Optional[discord.TextChannel] = None, b: Optional[discord.User] = None, c: int = 20
    ):
        channel, user, limit = a, b, c
        if channel is None:
            if user is None:
                raise commands.BadArgument("Invalid args")
            records = await Message_Log.fetch(user_id=user.id, order_by="message_id DESC", limit=limit)
        elif user is None:
            records = await Message_Log.fetch(channel_id=channel.id, order_by="message_id DESC", limit=limit)
        else:
            records = await Message_Log.fetch(
                channel_id=channel.id, user_id=user.id, order_by="message_id DESC", limit=limit
            )

        if not records:
            raise commands.BadArgument("No data")

        data = ""
        for _, message_id, _, user_id, content, _ in records:
            created_at = utils.snowflake_time(message_id)
            data += f"<@{user_id}> @ {human_friendly_timestamp(created_at)}: {content}\n\n"
        await ctx.send(data)


def setup(bot: BotBase):
    bot.add_cog(Snipe(bot))
