import datetime
from typing import Optional
import asyncpg

import discord
from discord.ext import commands, menus
from ditto.types.types import User
import humanize

from ditto import BotBase, Context, Cog
from ditto.db.scheduler import Events
from ditto.utils.paginator import EmbedPaginator
from ditto.utils.strings import ZWSP


from ditto.utils.files import get_base_dir


class Reminders(Cog):
    @staticmethod
    async def get_reminder(id: int) -> Optional[asyncpg.Record]:
        return await Events.fetchrow_where("id = $1 AND event_type = 'reminder'", id)

    @staticmethod
    async def get_reminders(user: User) -> list[asyncpg.Record]:
        return await Events.fetch_where("event_type = 'reminder' AND data #>> '{args,0}' = $1", str(user.id))

    @commands.group(aliases=["remind"], invoke_without_command=True)
    async def reminder(self, ctx: Context, *, argument: tuple[datetime.datetime, str]) -> None:
        """Set a reminder."""
        when, what = argument
        what = what or "..."

        if when <= ctx.message.created_at:
            raise commands.BadArgument("You can not set a reminder in the past")

        event = await self.bot.schedule_event(when, "reminder", ctx.author.id, ctx.channel.id, ctx.message.id, what)
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

    @reminder.command(name="clear")
    async def reminder_clear(self, ctx: Context) -> None:

        reminders = await self.get_reminders(ctx.author)

        if len(reminders) == 0:
            raise commands.BadArgument("You do not have any reminders.")

        if not await ctx.confirm("Are you sure you want to clear your reminders?"):
            await ctx.send("Cancelled..")
            return

        await Events.delete_where("event_type = 'reminder' AND data #>> '{args,0}' = $1", str(ctx.author.id))

        if self.bot.next_scheduled_event is not None:
            for reminder in reminders:
                if self.bot.next_scheduled_event.id == reminder["id"]:
                    self.bot.restart_scheduler()
                    break

        await ctx.send("Reminders cleared.")

    @reminder.command(name="cancel", aliases=["delete"])
    async def reminder_cancel(self, ctx: Context, *, id: int) -> None:

        reminder = await self.get_reminder(id)

        if reminder is None or reminder["data"]["args"][0] != ctx.author.id:
            raise commands.BadArgument(f"Reminder with ID: {id} not found.")

        await Events.delete_record(reminder)

        if getattr(self.bot.next_scheduled_event, "id", None) == id:
            self.bot.restart_scheduler()

        await ctx.send("Reminder deleted.")

    @reminder.command(name="list")
    async def reminder_list(self, ctx: Context) -> None:

        reminders = await self.get_reminders(ctx.author)

        if len(reminders) == 0:
            raise commands.BadArgument("You do not have any reminders.")

        embed = EmbedPaginator[discord.Embed](max_fields=8, colour=discord.Colour.blurple())
        embed.set_author(name=f"{ctx.author}'s Reminders", icon_url=ctx.author.avatar.url)
        embed.set_footer(text=f"{len(reminders)} reminder")

        for id, _, when, _, data in reminders:
            delta = when - ctx.message.created_at
            embed.add_field(name=f"{id}: In {humanize.precisedelta(delta, format='%0.0f')}:", value=data["args"][3])

        await menus.MenuPages(embed).start(ctx)

    @commands.Cog.listener()
    async def on_reminder(self, user_id: int, channel_id: int, message_id: int, what: str) -> None:
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
