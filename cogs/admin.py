from contextlib import redirect_stdout
from copy import copy
from io import StringIO
from textwrap import indent
from traceback import format_exc
from typing import Union

import discord
from discord.ext import commands

from bot import BotBase, Context
from utils.converters import Code
from utils.shell import AsyncShell


class Admin(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot
        self._ = None  # for eval env

    async def cog_check(self, ctx: Context):
        return await commands.is_owner().predicate(ctx)

    @commands.command()
    async def load(self, ctx: Context, *, extension: str):
        """Loads an extension.

        `extension`: The name of the extension.
        """
        try:
            self.bot.load_extension(extension)
            await ctx.tick()
        except commands.ExtensionError as e:
            raise commands.BadArgument(str(e)) from e

    @commands.command()
    async def unload(self, ctx: Context, *, extension: str):
        """Unloads an extension.

        `extension`: The name of the extension.
        """
        try:
            self.bot.unload_extension(extension)
            await ctx.tick()
        except commands.ExtensionError as e:
            raise commands.BadArgument(str(e)) from e

    @commands.group(invoke_without_command=None)
    async def reload(self, ctx: Context, *, extension: str):
        """Reloads an extension.

        `extension`: The name of the extension.
        """
        try:
            self.bot.reload_extension(extension)
            await ctx.tick()
        except commands.ExtensionError as e:
            raise commands.BadArgument(str(e)) from e

    @reload.command()
    async def config(self, ctx: Context):
        """Reloads the bot's config."""
        self.config.read('./config.ini')
        await ctx.tick()

    @commands.command()
    async def eval(self, ctx: Context, *, code: Code):
        """Evaluates python code.

        `code`: Python code to run.
        """
        env = {
            'bot': self.bot,
            'ctx': ctx,
            '_': self._
        }
        env.update(globals())

        stdout = StringIO()

        try:
            TAB = '\t'
            exec(f'async def func():\n{indent(code, TAB)}', env)
        except Exception as e:
            return await ctx.send(f'```py\n{type(e).__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                self._ = await func()
        except Exception:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{format_exc()}\n```')
        else:
            value = stdout.getvalue() or '...'
            await ctx.send(f'```py\n{value}\n```')

    @commands.command()
    async def sudo(self, ctx: Context, user: Union[discord.Member, discord.User], *, command: str):
        """Runs a command as another user.

        `user`: The user to run the command as.
        `command`: The command to run.
        """
        new_message = copy(ctx.message)
        new_message.author = user
        new_message.content = ctx.prefix + command
        new_ctx = await self.bot.get_context(new_message)
        try:
            await self.bot.invoke(new_ctx)
        except commands.CommandInvokeError as e:
            raise e.original

    @commands.command(aliases=['restart'])
    async def logout(self, ctx: Context):
        """Logs the bot out."""
        await ctx.tick()
        await ctx.bot.logout()

    @commands.command(aliases=['sh'])
    async def shell(self, ctx: Context, *, code: Code):
        """Executes a command in the shell.

        `code`: The command to run in the shell.
        """
        paginator = commands.Paginator(prefix='```sh')
        paginator.add_line(f'$ {code}\n')

        async with AsyncShell(code) as shell:
            async for line in shell:
                paginator.add_line(line)

        paginator.add_line(f'\n[status] Exit code {shell.exit_code}')

        for page in paginator.pages:
            await ctx.send(page)

    @commands.command()
    async def git(self, ctx: Context, *, code: Code):
        """Executes a git commmand.

        `code`: The git command to run.
        """
        await ctx.invoke(self.shell, code='git ' + code)


def setup(bot: BotBase):
    bot.add_cog(Admin(bot))
