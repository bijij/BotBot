from typing import Optional, Union

import bottom

import discord
from discord.ext import commands

from ditto import Context, Cog


class Bottom(Cog):
    @commands.group(aliases=["bottomify"])
    async def bottom(self, ctx: Context):
        """Bottom translation commands."""
        ...

    @bottom.command(name="bottomify", aliases=["b", "encode"])
    async def bottom_bottomify(self, ctx: Context, *, message: Optional[Union[discord.Message, str]] = None):
        """Encodes a messsage."""
        ref = ctx.message.reference
        if message is None:
            if isinstance(getattr(ref, "resolved", None), discord.Message):
                message = ref.resolved.content
            else:
                message = None

        if isinstance(message, discord.Message):
            message = message.content

        if message is None:
            await ctx.send("No message to encode.")

        await ctx.send(bottom.encode(message))

    @bottom.command(name="regress", aliases=["r", "decode"])
    async def bottom_regress(self, ctx: Context, *, message: Optional[Union[discord.Message, str]] = None):
        """Decodes a messsage."""
        ref = ctx.message.reference
        if message is None:
            if isinstance(getattr(ref, "resolved", None), discord.Message):
                message = ref.resolved.content
            else:
                message = None

        if isinstance(message, discord.Message):
            message = message.content

        if message is None:
            return await ctx.send("No message to decode.")

        try:
            await ctx.send(bottom.decode(message))
        except ValueError:
            await ctx.send("Failed to decode message.")


def setup(bot):
    bot.add_cog(Bottom(bot))
