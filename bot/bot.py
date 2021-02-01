import asyncio
import datetime
import logging
import traceback

import discord
from discord.ext import commands

from donphan import create_pool, create_types, create_tables, create_views, MaybeAcquire
from ampharos import setup as setup_ampharos

from .config import CONFIG
from .context import Context
from .handler import WebhookHandler
from .help import EmbedHelpCommand
from .timers import dispatch_timers

try:
    from cogs.memes.status import get_status
except ImportError:
    def get_status(_): return discord.Status.online  # noqa: E704


DPY_VOICE_GENERAL = 741656304359178271


class BotBase(commands.Bot):
    def __init__(self):
        self.start_time = datetime.datetime.utcnow()

        from utils.converters import ALL_CONVERTERS

        for typing, converter in ALL_CONVERTERS.items():
            self.converters[typing] = converter

        self.log = logging.getLogger(__name__)
        self.log.setLevel(CONFIG.LOGGING.LOG_LEVEL)

        log = logging.getLogger()
        log.setLevel(CONFIG.LOGGING.LOG_LEVEL_ALL)

        handler = WebhookHandler(CONFIG.LOGGING.WEBHOOK)
        log.addHandler(handler)
        log.addHandler(logging.StreamHandler())

        self.prefix = CONFIG.BOT.PREFIX

        allowed_mentions = discord.AllowedMentions.none()  # <3 Moogy
        intents = discord.Intents.all()
        status = get_status(self.start_time)

        super().__init__(command_prefix=commands.when_mentioned_or(self.prefix), help_command=EmbedHelpCommand(),
                         allowed_mentions=allowed_mentions, intents=intents, status=status)

        self._active_timer = asyncio.Event()
        self._current_timer = None
        self._timer_task = self.loop.create_task(dispatch_timers(self))

        self.whitelisted_users = set()

        def load_extension(extension):
            try:
                self.load_extension(f'{extension}')
            except commands.ExtensionFailed as e:
                self.log.error(f'Failed to load extension {extension}\n{type(e).__name__}: {e}')

        for extension in CONFIG.SECRET_EXTENSIONS.split(';'):
            load_extension(f"cogs.secret.{extension}")

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

        if message.channel.id == DPY_VOICE_GENERAL:
            if message.author.id not in self.whitelisted_users:
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
        await create_types()
        await create_tables()
        await create_views()
        await setup_ampharos()

        self._start_time = datetime.datetime.utcnow()

        return await super().connect(*args, **kwargs)

    def run(self):
        super().run(CONFIG.BOT.TOKEN)
