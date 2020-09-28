import asyncio
import datetime
import logging
import traceback

import discord
from discord.ext import commands

from donphan import create_pool, create_tables, create_views, MaybeAcquire
from ampharos import setup as setup_ampharos

from .config import CONFIG
from .context import Context
from .handler import WebhookHandler
from .help import EmbedHelpCommand
from .timers import dispatch_timers


class BotBase(commands.Bot):
    def __init__(self):
        self.start_time = datetime.datetime.utcnow()

        from utils.converters import __converters__

        for o, c in __converters__.items():
            self.converters[o] = c

        self.log = logging.getLogger(__name__)
        self.log.setLevel(CONFIG.LOGGING.LOG_LEVEL)

        log = logging.getLogger()
        log.setLevel(CONFIG.LOGGING.LOG_LEVEL_ALL)

        handler = WebhookHandler(CONFIG.LOGGING.WEBHOOK)
        log.addHandler(handler)
        log.addHandler(logging.StreamHandler())

        self.prefix = CONFIG.BOT.PREFIX

        intents = discord.Intents.all()

        super().__init__(command_prefix=commands.when_mentioned_or(self.prefix), help_command=EmbedHelpCommand(), intents=intents)

        self._active_timer = asyncio.Event()
        self._current_timer = None
        self._timer_task = self.loop.create_task(dispatch_timers(self))

        def load_extension(extension, prefix='cogs'):
            try:
                self.load_extension(f'{prefix}.{extension}')
            except commands.ExtensionFailed as e:
                self.log.error(f'Failed to load extension {extension}\n{type(e).__name__}: {e}')

        for extension in CONFIG.SECRET_EXTENSIONS.split(';'):
            load_extension(extension, prefix='cogs.secret')

        for extension in CONFIG.EXTENSIONS.keys():
            load_extension(extension)

    @property
    def uptime(self) -> float:
        return (datetime.datetime.utcnow() - self.start_time).total_seconds()

    async def on_ready(self):
        self.log.info(f'Logged in as {self.user} ({self.user.id})')
        await self.is_owner(self.user)  # fetch owner id
        if self.owner_id:
            self.owner = self.get_user(self.owner_id)

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

        error = error.__cause__  # type: ignore

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
        # setup database
        dsn = f"postgres://{CONFIG.DATABASE.USERNAME}:{CONFIG.DATABASE.PASSWORD}@localhost/{CONFIG.DATABASE.DATABASE}"

        await create_pool(dsn, server_settings={
            'application_name': 'BotBot'}
        )
        self.pool = MaybeAcquire().pool
        await create_tables(drop_if_exists=False)
        await create_views(drop_if_exists=False)
        await setup_ampharos()

        return await super().connect(*args, **kwargs)

    def run(self):
        super().run(CONFIG.BOT.TOKEN)
