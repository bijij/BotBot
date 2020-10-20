import inspect
import os
import pathlib

import discord
from discord.ext import commands

import psutil

from bot import BotBase, Context

from bot.config import CONFIG as BOT_CONFIG
from utils.tools import format_dt


class Meta(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

    @commands.command(name='about')
    async def about(self, ctx: Context):
        """Displays some basic information about the bot."""
        embed = discord.Embed(
            colour=ctx.me.colour,
            description=f'I am {self.bot.user}, a bot made by {self.bot.owner}. My prefix is `{self.bot.prefix}`.'
        ).set_author(name=f'About {self.bot.user.name}:', icon_url=self.bot.user.avatar_url)

        await ctx.send(embed=embed)

    @commands.command(name='status')
    async def status(self, ctx: Context):
        """Sends some basic status information"""
        # Get lines of code
        lines_of_code = os.popen(
            r'find . -path ./.venv -prune -false -o -name "*.py" -exec cat {} \; | wc -l').read()

        # Get memory usage
        process = psutil.Process(os.getpid())
        memory_usage = process.memory_info().rss / 1024 ** 2

        await ctx.send(
            embed=discord.Embed(
                title=f'{self.bot.user.name} Status',
                colour=self.bot.user.colour
            ).set_thumbnail(
                url=self.bot.user.avatar_url
            ).add_field(
                name='Users:', value=len(self.bot.users)
            ).add_field(
                name='Guilds:', value=len(self.bot.guilds)
            ).add_field(
                name='Started at:', value=format_dt(self.bot._start_time)
            ).add_field(
                name='Memory usage:', value=f'{memory_usage:.2f} MB'
            ).add_field(
                name='Cogs loaded:', value=len(self.bot.cogs)
            ).add_field(
                name='Lines of code:', value=lines_of_code or 'Unknown'
            ).add_field(
                name='Quick links:',
                value='[Source Code](https://github.com/bijij/Silvally)',
                inline=False
            )
        )

    @commands.command(name='source')
    async def source(self, ctx: Context, *, command: commands.Command = None):
        """Display's a command's source code."""
        if command is None:
            return await ctx.send(BOT_CONFIG.REPOSITORY_URL)  # type: ignore

        if command.name == 'help':
            code = type(self.bot.help_command)

        else:
            code = command.callback.__code__

        filename: str = inspect.getsourcefile(code)  # type: ignore
        filename = str(pathlib.Path(filename).relative_to(pathlib.Path.cwd())).replace('\\', '/')

        lines, first_line = inspect.getsourcelines(code)

        last_line = first_line + len(lines) - 1
        await ctx.send(f'{BOT_CONFIG.REPOSITORY_URL}/blob/master/{filename}#L{first_line}-#L{last_line}')  # type: ignore


def setup(bot: BotBase):
    bot.add_cog(Meta(bot))
