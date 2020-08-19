import asyncio
import datetime
import random

import discord
from discord.ext import commands, menus, tasks

import wavelink

from utils.paginator import EmbedPaginator

from .session import Session
from .track import YouTubeTrack, SoundCloudTrack, AttachmentTrack

ZWSP = "​"


async def session_is_not_running(ctx: commands.Context) -> bool:
    if ctx.cog._get_session(ctx.guild) is not None:
        raise commands.CheckFailure('A player is already running on this server.')
    return True


async def session_is_running(ctx: commands.Context) -> bool:
    if ctx.cog._get_session(ctx.guild) is None:
        raise commands.CheckFailure('A player is not running on this server.')
    return True


async def session_is_stoppable(ctx: commands.Context) -> bool:
    session = ctx.cog._get_session(ctx.guild)
    if session is None or not session.stoppable:
        raise commands.CheckFailure('This player session cannot be stopped.')
    return True


async def user_is_in_voice_channel(ctx: commands.Context) -> bool:
    if not isinstance(ctx.author, discord.Member) or ctx.author.voice is None:
        raise commands.CheckFailure(
            'You are currently not in a voice channel.')
    return True


async def user_is_listening(ctx: commands.Context) -> bool:
    session = ctx.cog._get_session(ctx.guild)
    if session is None or ctx.author.id not in session.listeners:
        raise commands.CheckFailure(
            'You are currently not listening to the bot.')
    return True


async def user_has_required_permissions(ctx: commands.Context) -> bool:
    session = ctx.cog._get_session(ctx.guild)
    if session is not None and not session.user_has_permission(ctx.author):
        raise commands.CheckFailure(
            f'Only users with the {session.config["requires_role"].mention} role can use this command.')
    return True


class Player(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._alone = asyncio.Event()
        self._restart.start()

        self.bot.loop.create_task(self.start_nodes())

    def cog_unload(self):
        self._restart.cancel()

    def _get_session(self, guild: discord.Guild) -> Session:
        if isinstance(guild.voice_client, Session):
            return guild.voice_client
        return None

    @commands.group(name='player')
    async def player(self, ctx):
        pass

    @player.command(name='start', aliases=['join'])
    @commands.check(user_is_in_voice_channel)
    @commands.check(session_is_not_running)
    async def start(self, ctx, *, log_channel: discord.TextChannel = None):
        """Starts a new player session."""
        session = await ctx.author.voice.channel.connect(cls=Session)
        session.setup(log_channel=log_channel)

    @player.command(name='stop', aliases=['leave', 'quit'])
    @commands.check(session_is_running)
    @commands.check(session_is_stoppable)
    async def stop(self, ctx):
        """Stops the currently running player session."""
        session = self._get_session(ctx.guild)
        listeners = list(session.listeners)

        if len(listeners) == 0:
            await session.disconnect(force=False)

        if ctx.author in session.stop_requests:
            raise commands.BadArgument('You have already requested to stop the player.')

        if ctx.author.id in listeners:
            session.stop_requests.append(ctx.author)

        stops_needed = len(listeners)
        if len(session.stop_requests) >= stops_needed:
            await session.disconnect(force=False)
        else:
            await ctx.send(embed=discord.Embed(
                colour=discord.Colour.dark_green(),
                title='Stop Player',
                description=f'You currently need **{stops_needed - len(session.stop_requests)}** more votes to stop the player.'
            ))

    @player.group(name='request', aliases=['play', 'p'], invoke_without_command=True)
    @commands.check(user_is_in_voice_channel)
    @commands.check(user_has_required_permissions)
    @commands.cooldown(2, 30, commands.BucketType.user)
    async def request(self, ctx, *, request: YouTubeTrack):
        """Adds a YouTube video to the requests queue.

        request: YouTube search query.
        """
        try:
            if not isinstance(request, AttachmentTrack):
                await ctx.message.delete()
        except discord.Forbidden:
            pass

        session = self._get_session(ctx.guild)

        # If there is no player session start one
        if session is None:
            session = await ctx.author.voice.channel.connect(cls=Session)
            session.setup(request=request)
        else:
            await user_is_listening(ctx)
            session.queue.add_request(request)

        await ctx.send(**request.request_message)

    @request.command(name='youtube', aliases=['yt'])
    @commands.check(user_is_in_voice_channel)
    @commands.check(user_has_required_permissions)
    async def request_youtube(self, ctx, *, request: YouTubeTrack):
        """Adds a YouTube video to the requests queue.

        request: YouTube search query.
        """
        if (await self.request.can_run(ctx)):
            await ctx.invoke(self.request, request=request)

    @request.command(name='soundcloud', aliases=['sc'])
    @commands.check(user_is_in_voice_channel)
    @commands.check(user_has_required_permissions)
    async def request_soundcloud(self, ctx, *, request: SoundCloudTrack):
        """Adds a SoundCloud track to the requests queue.

        request: SoundCloud search query.
        """
        if (await self.request.can_run(ctx)):
            await ctx.invoke(self.request, request=request)

    @request.command(name='file')
    @commands.check(user_is_in_voice_channel)
    @commands.check(user_has_required_permissions)
    async def request_file(self, ctx):
        """Adds a local file to the requests queue.

        `request`: The local file attached.
        """
        if not ctx.message.attachments:
            raise commands.BadArgument('You did not attach a file!')

        if (await self.request.can_run(ctx)):
            track = AttachmentTrack(ctx.message.attachments[0].url, ctx.author)
            await track.setup(self.bot)
            await ctx.invoke(self.request, request=track)

    @player.command(name='skip')
    @commands.check(session_is_running)
    @commands.check(user_is_listening)
    async def skip(self, ctx):
        """Skips the currently playing track."""
        session = self._get_session(ctx.guild)

        if ctx.author in session.skip_requests:
            raise commands.BadArgument('You have already requested to skip.')

        session.skip_requests.append(ctx.author)

        skips_needed = len(list(session.listeners)) // 2 + 1
        if len(session.skip_requests) >= skips_needed:
            await session.skip()
        else:
            await ctx.send(embed=discord.Embed(
                colour=discord.Colour.dark_green(),
                title='Skip track',
                description=f'You currently need **{skips_needed - len(session.skip_requests)}** more votes to skip this track.'
            ))

    @player.command(name='repeat', aliases=['encore', 'again'])
    @commands.check(session_is_running)
    @commands.check(user_is_listening)
    async def repeat(self, ctx):
        """Repeats the currently playing track."""
        session = self._get_session(ctx.guild)

        if ctx.author in session.repeat_requests:
            raise commands.BadArgument('You have already requested to repeat.')

        session.repeat_requests.append(ctx.author)

        repeats_needed = len(list(session.listeners)) // 2 + 1
        if len(session.repeat_requests) >= repeats_needed:
            session.queue.add_request(session.current_track, at_start=True)

            await ctx.send(embed=discord.Embed(
                colour=discord.Colour.dark_green(),
                title='Repeat track',
                description='This track has been re-added to the queue.'
            ))
        else:
            await ctx.send(embed=discord.Embed(
                colour=discord.Colour.dark_green(),
                title='Repeat track',
                description=f'You currently need **{repeats_needed - len(session.repeat_requests)}** more votes to repeat this track.'
            ))

    @player.command(name='volume', aliases=['set_volume', 'v', 'vol', 'set_vol'])
    @commands.check(session_is_running)
    @commands.check(user_is_listening)
    @commands.check(user_has_required_permissions)
    @commands.cooldown(2, 20, commands.BucketType.user)
    async def volume(self, ctx, volume: float = None):
        """Set's the global player volume"""
        session = self._get_session(ctx.guild)

        if volume is None:
            return await ctx.send(embed=discord.Embed(
                colour=discord.Colour.dark_green(),
                title='Volume change',
                description=f'Currently the player volume is set to {session.volume:.2f}%...'
            ))

        if volume < 0:
            raise commands.BadArgument('You can\'t set the volume to below 0%.')
        elif volume > 100:
            raise commands.BadArgument('You can\'t set the volume to above 100%.')

        await session.set_volume(volume)

        await ctx.send(embed=discord.Embed(
            colour=discord.Colour.dark_green(),
            title='Volume change',
            description=f'Setting volume to {volume:.2f}%...'
        ))

    @player.command(name='playing', aliases=['now', 'now_playing', 'np'])
    @commands.check(session_is_running)
    async def playing(self, ctx):
        """Retrieves information on the currently playing track."""
        session = self._get_session(ctx.guild)

        play_time = session.current_track_play_time
        track_length = session.current_track.length

        message = session.current_track.playing_message

        if track_length:
            play_time_str = str(datetime.timedelta(seconds=play_time))
            length_str = str(datetime.timedelta(seconds=track_length))

            seek_length = 50
            seek_distance = round(seek_length * play_time / track_length)

            message['embed'].add_field(
                name=f'{play_time_str} / {length_str}', value=f'`{"-" * seek_distance}|{"-" * (seek_length - seek_distance)}`', inline=False)

        await ctx.send(**message)

    @player.command(name='queue', aliases=['upcoming', 'next', 'q'])
    @commands.check(session_is_running)
    async def queue(self, ctx):
        """Displays the current request queue."""

        session = self._get_session(ctx.guild)

        total_length = session.current_track.length - session.current_track_play_time
        total_length += sum(track.length for track in session.queue.requests)
        length_str = str(datetime.timedelta(seconds=total_length))

        paginator = EmbedPaginator(
            colour=discord.Colour.dark_green(),
            title=f'Upcoming requests - Total Queue Length: {length_str}',
            max_fields=10
        )

        if not session.queue.requests:
            raise commands.UserInputError('There are currently no requests.')

        for index, track in enumerate(session.queue.requests, 1):
            paginator.add_field(
                name=f'{index} - Requested by {track.requester}',
                value=track.information,
                inline=False
            )

        try:
            if len(paginator.pages) == 1:
                return await ctx.send(embed=paginator.pages[0])
            menu = menus.MenuPages(paginator, clear_reactions_after=True, check_embeds=True)
            await menu.start(ctx)
        except discord.HTTPException:
            raise commands.BadArgument('I couldn\'t post the queue in this channel.')

    @player.group(name='force')
    @commands.check_any(commands.is_owner(), commands.has_permissions(administrator=True))
    async def force(self, ctx):
        """Admin commands."""
        pass

    @force.command(name='skip')
    @commands.check(session_is_running)
    async def force_skip(self, ctx):
        """Force skip the currently playing track."""
        session = self._get_session(ctx.guild)
        await session.skip()

    @force.command(name='stop', aliases=['leave'])
    @commands.check(session_is_running)
    async def force_stop(self, ctx):
        """Force the session to stop."""
        session = self._get_session(ctx.guild)
        await session.disconnect(force=False)

    @force.command(name='repeat', aliases=['encore', 'again'])
    @commands.check(session_is_running)
    async def force_repeat(self, ctx):
        """Force the currently track to be repeated."""
        session = self._get_session(ctx.guild)
        session.queue.add_request(session.current_track, at_start=True)

    @force.command(name='remove')
    @commands.check(session_is_running)
    async def force_remove(self, ctx, track_number: int):
        """Force remove a track from the queue"""
        session = self._get_session(ctx.guild)
        if track_number < 0 or track_number > len(session.queue.requests):
            raise commands.BadArgument('Track not in queue.')
        session.queue.requests.pop(track_number - 1)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        session = self._get_session(member.guild)
        if session is not None:
            if member.id not in session.listeners:
                for request_list in [session.skip_requests, session.repeat_requests, session.stop_requests]:
                    if member in request_list:
                        request_list.remove(member)

            await session.check_listeners()

            # Set alone flag for auto restart
            for voice_client in self.bot.voice_clients:
                if isinstance(voice_client, Session):
                    if session.not_alone.is_set():
                        return self._alone.clear()

            self._alone.set()

    @commands.Cog.listener('on_wavelink_track_stuck')
    @commands.Cog.listener('on_wavelink_track_end')
    @commands.Cog.listener('on_wavelink_track_exception')
    async def on_player_stop(self, session, **kwargs):
        await session.toggle_next()

    async def start_nodes(self):
        host = self.bot.config['PLAYER']['lavalink_address']
        await wavelink.Node.create(
            self.bot,
            host=host,
            port=2333,
            rest_uri=f'http://{host}:2333',
            password=self.bot.config['PLAYER']['lavalink_password'],
            identifier='BotBot',
            region=discord.VoiceRegion.us_east
        )

    @tasks.loop(hours=12)
    async def _restart(self):
        if self._restart.current_loop != 0:
            await self._alone.wait()
            self.bot.log.info('Automatically Restarting')
            await self.bot.logout()


def setup(bot: commands.Bot):
    bot.add_cog(Player(bot))
