import discord
from discord.ext import commands

from bot import BotBase, Context


class Meta(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

    @commands.command(name='about')
    async def about(self, ctx: Context):
        """Displays some basic information about the bot."""
        prefix = ctx.bot.config['BOT']['prefix']
        embed = discord.Embed(
            colour=ctx.me.colour,
            description=f'I am {self.bot.user}, a bot made by {self.bot.owner}. My prefix is `{prefix}`.'
        ).set_author(name=f'About {self.bot.user.name}:', icon_url=self.bot.user.avatar_url)

        await ctx.send(embed=embed)


def setup(bot: BotBase):
    bot.add_cog(Meta(bot))
