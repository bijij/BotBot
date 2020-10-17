import discord
from discord.ext import commands, menus

from humanize import precisedelta

from bot import BotBase, Context, timers
from utils.converters import WhenAndWhat
from utils.paginator import EmbedPaginator


class Reminders(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

    @commands.group(name='reminder', aliases=['remind'], invoke_without_command=True)
    async def reminder(self, ctx: Context, *, when_and_what: WhenAndWhat):
        """Reminds you of something after a certain amount of time.

        The input can be any direct date (e.g. YYYY-MM-DD) or a human
        readable offset. Examples:
        - 'next thursday at 3pm do something funny'
        - 'do the dishes tomorrow'
        - 'in 3 days do the thing'
        - '2d unmute someone'
        Times are in UTC.
        """

        expires_at, reminder = when_and_what

        if expires_at < ctx.message.created_at:
            raise commands.BadArgument('You cannot set a reminder in the past.')

        if reminder.lower().startswith(('me to ', 'me that ')):
            reminder = reminder.split(maxsplit=2)[-1]

        timer = await timers.create_timer(self.bot, expires_at, 'reminder', ctx.author.id, ctx.channel.id, ctx.message.id, reminder)

        delta = expires_at - ctx.message.created_at

        embed = discord.Embed(
            title=f'In {precisedelta(delta, format="%0.0f")}:',
            description=reminder
        ).set_author(
            name=f'Reminder for {ctx.author.name} set',
            icon_url=ctx.author.avatar_url
        )

        if timer.id is not None:
            embed.set_footer(text=f'Reminder ID #{timer.id} | Use {self.bot.prefix}reminder cancel {timer.id} to cancel this reminder.')

        await ctx.send(embed=embed)

    @reminder.group(name='list')
    async def reminder_list(self, ctx: Context):
        """List your upcoming reminders."""

        async with ctx.db as conn:
            records = await conn.fetch('SELECT * FROM core.timers WHERE event_type = \'reminder\' AND data #>> \'{args,0}\' = $1', str(ctx.author.id))

        if len(records) == 0:
            raise commands.BadArgument('You currently don\'t have any reminders set')

        paginator = EmbedPaginator(
            colour=discord.Colour.blurple(), max_fields=10
        ).set_author(
            name=f'{ctx.author.name}\'s reminders.', icon_url=ctx.author.avatar_url
        ).set_footer(text=f'Use {self.bot.prefix}reminder cancel id to cancel a reminder.')

        for id, _, expires_at, _, data in records:
            delta = expires_at - ctx.message.created_at
            paginator.add_field(name=f'ID #{id}: In {precisedelta(delta, format="%0.0f")}', value=data['args'][3])

        menu = menus.MenuPages(paginator, clear_reactions_after=True, check_embeds=True)
        await menu.start(ctx)

    @reminder.group(name='cancel', aliases=['delete'])
    async def reminder_cancel(self, ctx: Context, id: int):
        """Cancel an upcoming reminder."""

        async with ctx.db as conn:
            record = await conn.fetchrow('SELECT * FROM core.timers \
                WHERE id = $1 AND event_type = \'reminder\' AND data #>> \'{args,0}\' = $2', id, str(ctx.author.id))
            if record is None:
                raise commands.BadArgument(f'Could not find a reminder with id #{id}')

            await timers.delete_timer(self.bot, record, connection=conn)

        await ctx.tick()

    @commands.Cog.listener()
    async def on_reminder_timer_complete(self, user_id, channel_id, message_id, reminder):

        user = self.bot.get_user(user_id)
        channel = self.bot.get_channel(channel_id)

        # Return if the user could not be found
        if user is None:
            return

        if channel_id is not None and not isinstance(channel, discord.DMChannel):
            guild_id = channel.guild.id
        else:
            guild_id = '@me'

        # DM To user if channel is deleted
        if channel is None:
            channel = user

        embed = discord.Embed(
            colour=discord.Colour.blurple(),
            description=reminder
        ).set_author(
            name=f'Reminder for {user.name}.', icon_url=user.avatar_url
        ).add_field(
            name='Jump URL:', value=f'[Jump!](<https://discord.com/channels/{guild_id}/{channel_id}/{message_id}>)'
        )

        allowed_mentions = discord.AllowedMentions(users=True)
        await channel.send(user.mention, embed=embed, allowed_mentions=allowed_mentions)


def setup(bot: BotBase):
    bot.add_cog(Reminders(bot))
