import asyncio
import re

# from functools import partial
from difflib import SequenceMatcher
from pathlib import Path
from io import BytesIO
from typing import Dict, List, Tuple

# import aiohttp
import wavelink

import discord
from discord.ext import commands

from utils import tools


class Track:
    requester = None
    _embed_colour = discord.Colour.blurple()
    _track_type = 'Track'

    def __init__(self, url: str, requester: discord.User = None, track: wavelink.Track = None):
        self.url = url
        self.requester = requester
        self.track = track

    async def setup(self, bot) -> wavelink.Track:
        """Prepares a wavelink track object for playing."""
        if self.track is None:
            data = await wavelink.Node.get_best_node(bot).get_tracks(self.url)

            if not data:
                raise commands.BadArgument('Error loading track.')

            self.track = data.pop(0)

        return self.track

    @property
    def length(self) -> int:
        if self.track is not None:
            return self.track.length // 1000
        return 0

    @property
    def _title(self):
        return self.track.title

    @property
    def _author(self):
        return self.track.author

    @property
    def information(self) -> str:
        """Provides basic information on a track

        An example of this would be the title and artist.
        """
        return f"**{self._title}** by **{self._author}**"

    @property
    def status_information(self) -> str:
        """Provides basic information on a track for use in the discord status section

        An example of this would be the title and artist.
        """
        return f"{self._title} by {self._author}"

    @property
    def playing_message(self) -> Dict:
        """A discord embed with more detailed information to be displayed when a track is playing."""
        return {
            'embed': discord.Embed(
                colour=self._embed_colour,
                description=self.information
            )
        }

    @property
    def request_message(self) -> Dict:
        """A discord Embed with basic information to be displayed when a track is requested."""
        return {
            'embed': discord.Embed(
                colour=self._embed_colour,
                description=f'Adding {self.information} to the queue...'
            ).set_author(
                name=f'{self._track_type} - Requested by {self.requester}'
            )
        }

    @classmethod
    async def convert(cls, ctx: commands.Converter, argument: str):
        raise NotImplementedError

    @classmethod
    async def get_user_choice(cls, ctx: commands.Context, search_query: str, entries: List[Tuple[str, str]]) -> int:
        embed = discord.Embed(
            colour=cls._embed_colour,
        ).set_author(
            name=f'{cls._track_type} search results - {search_query} - Requested by {ctx.author}'
        ).set_footer(text=f'Select a search result or {tools.regional_indicator("x")} to cancel.')

        for index, entry in enumerate(entries, 1):
            embed.add_field(
                name=f'{index} - {entry[0]}', value=entry[1], inline=False)

        search_message = (await ctx.send(embed=embed))
        reactions = [tools.keycap_digit(n) for n in range(1, 1 + len(entries))]
        reactions.append(tools.regional_indicator('x'))
        await tools.add_reactions(search_message, reactions)

        def check(reaction: discord.Reaction, user: discord.User):
            return reaction.message.id == search_message.id and user == ctx.author \
                and reaction.emoji in reactions

        try:
            reaction, _ = await ctx.bot.wait_for('reaction_add', check=check, timeout=60)
        except asyncio.TimeoutError:
            raise commands.BadArgument(
                'You did not choose a search result in time.')
        finally:
            await search_message.delete()

        if reaction.emoji == tools.regional_indicator('x'):
            raise commands.BadArgument('Selection cancelled.')

        return int(reaction.emoji[0]) - 1


class StreamableTrack(Track):
    _track_type = 'Unknown Stream'
    _search_type = ''

    @property
    def _url(self):
        return '#'

    @property
    def _thumbnail(self):
        return self.track.thumb

    @property
    def information(self) -> str:
        return f'**[{self._title}]({self._url})** by **{self._author}**'

    @property
    def playing_message(self) -> Dict:
        embed = discord.Embed(
            colour=self._embed_colour,
            description=f'[{self._title}]({self._url})'
        ).set_author(name=f'{self._author} - Requested By: {self.requester}')

        if self._thumbnail:
            embed.set_thumbnail(url=self._thumbnail)

        return {
            'embed': embed
        }

    @classmethod
    async def convert(cls, ctx: commands.Converter, argument: str):
        async with ctx.typing():

            tracks = await wavelink.Node.get_best_node(ctx.bot).get_tracks(cls._search_type + argument)
            if not isinstance(tracks, list):
                raise commands.BadArgument('No search results were found.')

            tracks = [cls(argument, ctx.author, track) for track in tracks[:int(ctx.bot.config['PLAYER']['max_search_results'])]]
            if len(tracks) == 1:
                return tracks[0]

            choice = await cls.get_user_choice(ctx, argument, [(track._title, track._author) for track in tracks])
            return tracks[choice]


class YouTubeTrack(StreamableTrack):
    _embed_colour = discord.Colour.red()
    _track_type = 'YouTube video'
    _search_type = 'ytsearch:'

    video_url_check = re.compile(
        r'(?:youtube(?:-nocookie)?\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})')

    # region metadata

    @property
    def _url(self):
        return f'https://youtu.be/{self.track.identifier}'

    # endregion

    @classmethod
    async def convert(cls, ctx: commands.Converter, argument: str):
        # If user directly requested youtube video
        is_video = cls.video_url_check.search(argument)
        if is_video is not None:
            track = cls(argument, ctx.author)
            await track.setup(ctx.bot)
            return track

        return await super().convert(ctx, argument)


class SoundCloudTrack(StreamableTrack):
    _embed_colour = discord.Colour.orange()
    _track_type = 'SoundCloud track'
    _search_type = 'scsearch:'

    @property
    def _url(self):
        return self.track.info['uri']


class AttachmentTrack(StreamableTrack):
    _embed_colour = discord.Colour.blue()
    _track_type = 'Local file'

    @property
    def _title(self):
        if self.track is not None:
            if not self.track.title.isdigit():
                return self.track.title
        return 'File'

    @property
    def _author(self):
        if self.track is not None:
            if self.track.author != 'Unknown artist':
                return self.track.author
        return self.requester.name

    @classmethod
    async def convert(cls, ctx: commands.Context, argument: str):
        raise NotImplementedError
