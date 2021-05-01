import discord
from discord.ext import commands

from ditto import BotBase, Cog

from donphan import Column, Table, SQLType
from donphan.connection import MaybeAcquire


class Voice_Log_Configuration(Table, schema="logging"):  # type: ignore
    guild_id: Column[SQLType.BigInt] = Column(primary_key=True)
    log_channel_id: Column[SQLType.BigInt]
    display_hidden_channels: Column[bool] = Column(default=True)


class VoiceLogging(Cog):
    def __init__(self, bot: BotBase):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):

        # TODO: Perms in

        if before.channel == after.channel:
            return

        # if not record['display_hidden_channels']:
        #     # Handle hidden channel case
        #     base_member = discord.Object(0)
        #     base_member._roles = {member.guild.id}

        #     if before.channel is None or not before.channel.permissions_for(base_member).view_channel:
        #         if after.channel is None or not after.channel.permissions_for(base_member).view_channel:
        #             return
        #         return await self.on_voice_state_join(channel, member, after)

        #     if after.channel is None or not after.channel.permissions_for(base_member).view_channel:
        #         return await self.on_voice_state_leave(channel, member, before)

        # On Join
        if before.channel is None:
            return self.bot.dispatch("voice_state_join", member, after)

        # On Leave
        if after.channel is None:
            return self.bot.dispatch("voice_state_leave", member, before)

        # On Move
        return self.bot.dispatch("voice_state_move", member, before, after)

    @commands.Cog.listener()
    async def on_voice_state_join(self, member: discord.Member, after: discord.VoiceState):

        async with MaybeAcquire(pool=self.bot.pool) as connection:

            # Fetch DB entry
            record = await Voice_Log_Configuration.fetch_row(connection, guild_id=member.guild.id)
            if record is None:
                return

        channel = self.bot.get_channel(record["log_channel_id"])
        if channel is None:
            return

        await channel.send(
            embed=discord.Embed(
                colour=discord.Colour.green(),
                description=f"{member.mention} joined **{after.channel.name}**.",
                timestamp=discord.utils.utcnow(),
            ).set_footer(text="Server log update", icon_url=member.avatar.url)
        )

    @commands.Cog.listener()
    async def on_voice_state_move(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        async with MaybeAcquire(pool=self.bot.pool) as connection:

            # Fetch DB entry
            record = await Voice_Log_Configuration.fetch_row(connection, guild_id=member.guild.id)
            if record is None:
                return

        channel = self.bot.get_channel(record["log_channel_id"])
        if channel is None:
            return

        await channel.send(
            embed=discord.Embed(
                colour=discord.Colour.blue(),
                description=f"{member.mention} moved from **{before.channel.name}** to **{after.channel.name}**.",
                timestamp=discord.utils.utcnow(),
            ).set_footer(text="Server log update", icon_url=member.avatar.url)
        )

    @commands.Cog.listener()
    async def on_voice_state_leave(self, member: discord.Member, before: discord.VoiceState):

        async with MaybeAcquire(pool=self.bot.pool) as connection:
            # Fetch DB entry
            record = await Voice_Log_Configuration.fetch_row(connection, guild_id=member.guild.id)
            if record is None:
                return

        channel = self.bot.get_channel(record["log_channel_id"])
        if channel is None:
            return

        await channel.send(
            embed=discord.Embed(
                colour=discord.Colour.red(),
                description=f"{member.mention} left **{before.channel.name}**.",
                timestamp=discord.utils.utcnow(),
            ).set_footer(text="Server log update", icon_url=member.avatar.url)
        )


def setup(bot: BotBase):
    bot.add_cog(VoiceLogging(bot))
