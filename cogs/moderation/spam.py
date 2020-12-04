import datetime

from functools import cached_property
from typing import Dict, Optional

import discord
from discord.ext import commands

from donphan import Column, SQLType, Table

from bot import BotBase  # , Context


class CooldownByContent(commands.CooldownMapping):
    def _bucket_key(self, message):
        return (message.channel.id, message.content)


class GlobalCoolDown(commands.CooldownMapping):
    def _bucket_key(self, message):
        return (message.guild.id, message.author.id)

    def is_in_cache(self, message, current=None):
        if self._cooldown.type is commands.BucketType.default:
            return True

        self._verify_cache_integrity(current)
        key = self._bucket_key(message)
        return key in self._cache


class Spam_Checker(Table, schema='moderation'):  # type: ignore
    guild_id: SQLType.BigInt = Column(primary_key=True)
    max_mentions: int


class SpamCheckerConfig:
    guild_id: int
    # mention_spam_channel_ids: List[int]
    max_mentions: Optional[int]

    def __init__(self, bot: BotBase, record):
        self.bot = bot
        self.__dict__.update(record)

        self.content_bucket = CooldownByContent.from_cooldown(15, 17.0, commands.BucketType.member)
        self.user_bucket = commands.CooldownMapping.from_cooldown(10, 12.0, commands.BucketType.user)
        self.just_joined_bucket = commands.CooldownMapping.from_cooldown(10, 12, commands.BucketType.channel)
        self.new_user_bucket = commands.CooldownMapping.from_cooldown(30, 35.0, commands.BucketType.channel)

    @cached_property
    def guild(self) -> discord.Guild:
        return self.bot.get_guild(self.guild_id)

    # @property
    # def mention_spam_channels(self) -> List[discord.TextChannel]:
    #     return [v for c in self.mention_spam_channel_ids if (v := self.bot.get_channel(c)) is not None]

    @classmethod
    def user_just_joined(cls, message: discord.Message) -> bool:
        return (message.created_at - message.author.joined_at).total_seconds() < 1800

    @classmethod
    def user_is_new(cls, message: discord.Message) -> bool:
        account_is_new = message.author.created_at > message.created_at - datetime.timedelta(days=50)
        recently_joined_server = message.author.joined_at > message.created_at - datetime.timedelta(days=7)
        return account_is_new and recently_joined_server

    def is_spamming(self, message) -> bool:

        buckets = [self.user_bucket, self.content_bucket]

        if self.user_just_joined(message):
            buckets.append(self.just_joined_bucket)

        if self.user_is_new(message):
            buckets.append(self.new_user_bucket)

        current = message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp()

        for bucket in buckets:
            if bucket.get_bucket(message).update_rate_limit(current):
                return True

        return False

    async def check_mentions(self, message: discord.Message) -> bool:
        if self.max_mentions is None:
            return False

        mentions = {m for m in message.mentions if not m.bot and m != message.author}

        if (mention_count := len(mentions)) < self.max_mentions:
            return False

        # if message.channel in self.mention_spam_channels:
        #     return False

        try:
            await message.author.ban(reason=f'Reaction spam ({mention_count} mentions)')
        except Exception:
            self.bot.log.info(f'Failed to auto ban member {message.author} (ID: {message.author.id}) in guild {message.guild}')

        return True

    async def check_spam(self, message) -> bool:

        if not self.is_spamming(message):
            return False

        try:
            await message.author.ban(reason='Message spam')
        except Exception:
            self.bot.log.info(f'Failed to auto ban member {message.author} (ID: {message.author.id}) in guild {message.guild}')

        return True


class SpamChecker(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot
        self.config: Dict[discord.Guild, SpamCheckerConfig] = {}

        self.bot.loop.create_task(self.load_config())

    async def load_config(self):
        await self.bot.wait_until_ready()

        for record in await Spam_Checker.fetchall():
            config = SpamCheckerConfig(self.bot, record)
            if config.guild is not None:
                self.config[config.guild] = config

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore DMS
        if message.guild is None:
            return

        # Ignore Webhooks / System Messages
        if not isinstance(message.author, discord.Member):
            return

        # Ignore users with roles
        if len(message.author.roles) > 1:
            return

        # Ignore self and owner
        if message.author in {self.bot.user, self.bot.owner}:
            return

        # Ignore bots
        if message.author.bot:
            return

        # Ignore non-configured guilds
        if message.guild not in self.config:
            return
        config = self.config[message.guild]

        # Check for spam
        if await config.check_mentions(message):
            return
        if await config.check_spam(message):
            return


def setup(bot: BotBase):
    bot.add_cog(SpamChecker(bot))
