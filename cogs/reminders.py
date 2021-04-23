import datetime

import discord
from discord.ext import commands
import humanize

from ditto import BotBase, Context, Cog
from ditto.utils.strings import ZWSP


class Reminders(Cog):
    @commands.group(aliases=["remind"], invoke_without_command=True)
    async def reminder(
        self, ctx: Context, *, argument: tuple[datetime.datetime, str]
    ) -> None:
        """Set a reminder."""
        when, what = argument
        what = what or "..."

        if when <= ctx.message.created_at:
            raise commands.BadArgument("You can not set a reminder in the past")

        event = await self.bot.schedule_event(
            when, "reminder", ctx.author.id, ctx.channel.id, ctx.message.id, what
        )
        delta = when - ctx.message.created_at

        embed = discord.Embed(
            title=f"In {humanize.precisedelta(delta, format='%0.0f')}:",
            description=what,
        )
        embed.set_author(name="Reminder set")

        if event.id is not None:
            embed.set_footer(
                text=f"Reminder ID: {event.id} | Use {self.bot.prefix}reminder cancel {event.id} to cancel this reminder."
            )

        await ctx.reply(embed=embed)

    @commands.Cog.listener()
    async def on_reminder(
        self, user_id: int, channel_id: int, message_id: int, what: str
    ) -> None:
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        except discord.NotFound:
            return

        channel = self.bot.get_channel(channel_id)

        guild_id = getattr(getattr(channel, "guild", None), "id", "@me")

        jump_url = f"https://discord.com/channels/{guild_id}/{channel.id}/{message_id}"

        embed = (
            discord.Embed(colour=discord.Colour.blurple(), description=what)
            .set_author(name=f"Reminder for {user}.", icon_url=user.avatar.url)
            .add_field(name=ZWSP, value=f"[Jump!]({jump_url})")
        )

        if channel is not None:
            reference = discord.PartialMessage(channel=channel, id=message_id)
            await channel.send(embed=embed, reference=reference, mention_author=True)
            return

        await user.send(user.mention, embed=embed, mention_author=True)


def setup(bot: BotBase):
    bot.add_cog(Reminders(bot))
