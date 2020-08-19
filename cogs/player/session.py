import asyncio

from contextlib import suppress
from typing import Generator, List

import discord
from discord.ext import commands
import wavelink

from .queue import Queue
from .track import Track


class Session(wavelink.Player):

    def __init__(self, bot: discord.Client, voice_channel: discord.VoiceChannel):
        """

        Args:
            voice_channel (discord.VoiceChannel): The voice channel the session should start playing in.

        Kwargs:
            log_channel (discord.TextChannel): Specifies a channel to log playback history.

        """
        super().__init__(bot, voice_channel)

    def setup(self, *, log_channel: discord.TextChannel = None, request: Track = None, **kwargs):
        self.log_channel = log_channel
        self.config = kwargs
        self.queue_config = self.config.get('queue')

        self.not_alone = asyncio.Event()
        self.timeout = self.config.get('timeout') or int(self.client.config['PLAYER']['default_timeout'])

        self.skip_requests: List[discord.User] = list()
        self.repeat_requests: List[discord.User] = list()
        self.stop_requests: List[discord.User] = list()

        self.current_track = None

        self.queue = Queue(self.queue_config)

        if request is not None:
            self.queue.add_request(request)

        self.volume = self.config.get('default_volume') or int(self.client.config['PLAYER']['default_volume'])

        self.play_next_song = asyncio.Event()

        asyncio.create_task(self.session_task())

    @property
    def current_track_play_time(self) -> int:
        return self.position // 1000

    @property
    def listeners(self) -> Generator[int, None, None]:
        """Members listening to this session.

        A member is classified as a listener if:
            - They are the not the bot
            - They are not deafened

        Returns:
            `generator` of `int`: A generator consisting of the user_id's of members listening to the bot.

        """
        if self.channel is None:
            return

        for user_id, state in self.channel.voice_states.items():
            if user_id != self.client.user.id and not (state.deaf or state.self_deaf):
                yield user_id

    def user_has_permission(self, user: discord.Member) -> bool:
        """Checks if a user has permission to interact with this session."""
        if self.config.get('requires_role') is not None:
            return self.config.get('requires_role') in user.roles
        return True

    async def toggle_next(self):
        """Sets the next track to start playing"""
        self.current_track = self.queue.next_track()

        # if no more tracks in queue exit
        if self.current_track is None:
            await self.disconnect(force=False)
            return

        # Clear the queues
        self.skip_requests.clear()
        self.repeat_requests.clear()

        # Create wavelink object for track
        try:
            track = await self.current_track.setup(self.client)
        except commands.BadArgument:
            self.client.log.error(f'Failed to play track {self.current_track._title!r}.')
            await asyncio.sleep(1)

        # If server has log channel log new track
        if self.log_channel is not None:
            with suppress(discord.HTTPException):
                await self.log_channel.send(**self.current_track.playing_message)

        # Play the new track
        await self.play(track)

    async def skip(self):
        """Skips the currently playing track"""
        await self.stop()

    async def check_listeners(self):
        """Checks if there is anyone listening and pauses / resumes accordingly."""
        if len(list(self.listeners)) > 0:
            if self.is_paused():
                await self.resume()
                self.not_alone.set()
        elif not self.is_paused():
            await self.set_pause(True)
            self.not_alone.clear()

            # Wait to see if the bot stays alone for it's max timeout duration
            try:
                await asyncio.wait_for(self.not_alone.wait(), self.timeout)
            except asyncio.TimeoutError:
                self.disconnect(force=False)

    async def session_task(self):
        try:
            await self.set_volume(self.volume)
            await self.toggle_next()
            await self.check_listeners()
        except Exception:
            self.client.log.error('Exception in session', exc_info=True, stack_info=True)
