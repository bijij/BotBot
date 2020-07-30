import datetime
import logging
import traceback

from configparser import ConfigParser

import discord
from discord.ext import commands

from .context import Context
from .db import create_pool
from .handler import WebhookHandler
from .help import EmbedHelpCommand


class BotBase(commands.Bot):
    def __init__(self):
        self.start_time = datetime.datetime.utcnow()
        self.config = ConfigParser()
        self.config.read('./config.ini')

        from utils.converters import __converters__

        for o, c in __converters__.items():
            self.converters[o] = c

        self.log = logging.getLogger(__name__)
        self.log.setLevel(self.config['BOT']['log_level'])

        log = logging.getLogger()
        log.setLevel(self.config['BOT']['log_level_all'])

        handler = WebhookHandler(self.config['DISCODO']['WEBHOOK'])
        log.addHandler(handler)
        log.addHandler(logging.StreamHandler())

        super().__init__(command_prefix=commands.when_mentioned_or(self.config['BOT']['prefix']), help_command=EmbedHelpCommand())

        for extension in self.config['BOT']['startup_extensions'].split(','):
            try:
                self.load_extension(f'cogs.{extension}')
            except commands.ExtensionFailed as e:
                self.log.error(f'Failed to load extension {extension}\n{type(e).__name__}: {e}')

    @property
    def uptime(self) -> float:
        return (datetime.datetime.utcnow() - self.start_time).total_seconds()

    async def on_ready(self):
        self.log.info(f'Logged in as {self.user} ({self.user.id})')

    async def on_error(self, event_method, *args, **kwargs):
        self.log.exception(f'Ignoring exception in {event_method}\n')

    async def on_command_error(self, ctx: Context, error: Exception):
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, (commands.CheckFailure, commands.UserInputError, commands.CommandOnCooldown,
                              commands.MaxConcurrencyReached, commands.DisabledCommand)):
            return await ctx.send(
                embed=discord.Embed(
                    colour=discord.Colour.red(),
                    title=f'Error with command: {ctx.command.qualified_name}',
                    description=str(error)
                )
            )

        error = error.__cause__

        await ctx.send(
            embed=discord.Embed(
                colour=discord.Colour.dark_red(),
                title=f'Error with command: {ctx.command.qualified_name}',
                description=f'```py\n{type(error).__name__}: {error}\n```',
            ).set_footer(
                text='The developers have been made aware of this.'
            )
        )

        tb = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        self.log.error(f'Ignoring exception in command: {ctx.command.qualified_name}\n\n{type(error).__name__}: {error}\n\n{tb}')

    async def process_commands(self, message):
        if message.author.bot:
            return

        ctx = await self.get_context(message, cls=Context)
        await self.invoke(ctx)

    async def connect(self, *args, **kwargs):
        self.pool = await create_pool(self.config['DATABASE']['dsn'])
        return await super().connect(*args, **kwargs)

    def run(self):
        super().run(self.config['DISCODO']['token'])
