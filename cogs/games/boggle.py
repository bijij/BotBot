import asyncio
from enum import unique
import random

from collections import defaultdict
from string import ascii_uppercase
from typing import List, NamedTuple, Set

import discord
from discord.ext import commands, menus
from discord.message import Message
from discord.utils import cached_property

from bot import BotBase, Context
from utils.tools import ordinal


QU_EMOJI = '<:_:806844322346565662>'

COLUMNS = 4
ROWS = 4

REGIONAL_INDICATOR_EMOJI = (
    '\N{REGIONAL INDICATOR SYMBOL LETTER A}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER B}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER C}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER D}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER E}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER F}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER G}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER H}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER I}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER J}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER K}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER L}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER M}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER N}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER O}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER P}',
    QU_EMOJI,
    '\N{REGIONAL INDICATOR SYMBOL LETTER R}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER S}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER T}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER U}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER V}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER W}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER X}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER Y}',
    '\N{REGIONAL INDICATOR SYMBOL LETTER Z}',
)

with open('res/boggle.txt') as f:
    DICTIONARY = set(f.read().splitlines())


LETTERS_EMOJI = {letter: emoji for letter, emoji in zip(ascii_uppercase, REGIONAL_INDICATOR_EMOJI)}

DIE = [
    "RIFOBX", "IFEHEY", "DENOWS", "UTOKND",
    "HMSRAO", "LUPETS", "ACITOA", "YLGKUE",
    "QBMJOA", "EHISPN", "VETIGN", "BALIYT",
    "EZAVND", "RALESC", "UWILRG", "PACEMD"
]

POINTS = {
    3: 1,
    4: 1,
    5: 2,
    6: 3,
    7: 5,
} | {x: 11 for x in range(8, 17)}


class Position(NamedTuple):
    col: int
    row: int


class Board:

    def __init__(self):
        random.shuffle(DIE)
        self.columns = [[random.choice(DIE[row * COLUMNS + column]) for column in range(COLUMNS)] for row in range(ROWS)]

    def board_contains(self, word: str, pos: Position = None, passed: List[Position] = []) -> bool:
        # Empty words
        if len(word) == 0:
            return True

        # When starting out
        if pos is None:
            for col in range(COLUMNS):
                for row in range(ROWS):
                    if self.board_contains(word, Position(col, row)):
                        return True

        # Check adjacent for next letter
        elif word[0] == self.columns[pos.col][pos.row]:
            for x in range(-1,2):
                for y in range(-1,2):

                    # don't check yourself
                    if x == 0 and y == 0:
                        continue

                    new_col = pos.col + x
                    new_row = pos.row + y

                    if Position(new_col, new_row) in passed:
                        continue

                    if 0 <= new_col < COLUMNS and 0 <= new_row < ROWS:
                        if self.board_contains(word[1 if word[0] != 'Q' else 2:], Position(new_col, new_row), [*passed, pos]):
                            return True

        # Otherwise cannot find word
        return False

    @cached_property
    def legal_words(self) -> Set[str]:
        return {word for word in DICTIONARY if self.is_legal(word)}

    def is_legal(self, word: str) -> bool:
        if len(word) < 3:
            return False
        word = word.upper()
        if word not in DICTIONARY:
            return False
        return self.board_contains(word)

    def points(self, word: str) -> int:
        return POINTS[len(word)] if self.is_legal(word) else 0

    def total_points(self, words: List[str]) -> int:
        return sum(self.points(word) for word in words)


class Game(menus.Menu):

    def __init__(self, **kwargs):
        self.board = Board()
        self.setup()
        super().__init__(**kwargs)

    @property
    def state(self):
        state = ''

        for row in range(ROWS):
            emoji = []
            for column in range(COLUMNS):
                emoji.append(LETTERS_EMOJI[self.board.columns[column][row]])

            state = ' '.join(emoji) + '\n' + state

        return discord.Embed(description=state)

    def setup(self):
        raise NotImplementedError

    async def send_initial_message(self, ctx, channel):
        return await channel.send(content="Boggle game started, you have 3 minutes!", embed=self.state)

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)
        await self.bot.loop.run_in_executor(None, lambda: self.board.legal_words)

    async def check_message(self, message: discord.Message):
        raise NotImplementedError

    @menus.button('\N{BLACK SQUARE FOR STOP}\ufe0f', position=menus.Last(0))
    async def cancel(self, payload):
        await self.message.edit(content='Game Cancelled.')
        self.stop()


class DiscordGame(Game):

    @property
    def scores(self):
        embed = discord.Embed()

        i = 0
        old = None

        for user, words in sorted(self.words.items(), key=lambda v: self.board.total_points(v[1]), reverse=True):
            points = self.board.total_points(words)

            if points != old:
                old = points
                i += 1

            embed.add_field(name=f'{ordinal(i)}: {user}', value=f'**{len(words)}** words, **{points}** points.', inline=False)

        return embed

    def setup(self):
        self.all_words = set()
        self.words = defaultdict(set)

    async def check_message(self, message: discord.Message):
        word = message.content
        if word is None:
            return

        if not word.isalpha():
            return
        word = word.upper()

        if word not in self.board.legal_words:
            return

        if word in self.all_words:
            return
        
        # Add to user words
        self.all_words.add(word)
        self.words[message.author].add(word)

        await message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    async def finalize(self, timed_out: bool):
        if not timed_out:
            return
        await self.message.edit(content='Game Over!')
        await self.message.reply(embed=self.scores)


class ClassicGame(Game):

    @property
    def scores(self):
        embed = discord.Embed()

        i = 0
        old = None

        for user, unique in sorted(self.unique_words.items(), key=lambda v: self.board.total_points(v[1]), reverse=True):
            words = self.words[user]
            points = self.board.total_points(unique)

            if points != old:
                old = points
                i += 1

            embed.add_field(name=f'{ordinal(i)}: {user}', value=f'**{len(words)}** words, **{len(unique)}** unique, **{points}** points.', inline=False)

        return embed

    def filter_lists(self):
        for user, word_list in self.word_lists.items():
            
            for word in word_list.split():
                word = word.strip().upper()

                if not word.isalpha():
                    continue
                
                if word not in self.board.legal_words:
                    continue

                self.words[user].add(word)

                # Remove from all sets if not unique
                if word in self.used_words:
                    for list in self.unique_words.values():
                        if word in list:
                            list.remove(word)
                    continue

                self.used_words.add(word)
                self.unique_words[user].add(word)

    async def check_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        if not self.over:
            return

        if message.content is None:
            return

        if message.author in self.word_lists:
            return

        self.word_lists[message.author] = message.content
        await message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    def setup(self):
        self.over = False
        self.used_words = set()
        self.word_lists = dict()
        self.words = defaultdict(set)
        self.unique_words = defaultdict(set)

    async def finalize(self, timed_out: bool):
        if not timed_out:
            return
        await self.message.edit(content='Game Over!')
        await self.message.reply('Game Over! you have 10 seconds to send in your words.')
        self.over = True
        await asyncio.sleep(10)
        self.filter_lists()
        await self.message.reply(embed=self.scores)


class Boggle(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot
        self.games = defaultdict(lambda: None)

    @commands.command()
    @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def boggle(self, ctx: Context, type: str = 'discord'):
        """Start a game of boggle."""
        if type.lower() == 'classic':
            self.games[ctx.channel] = game = ClassicGame()
        else:
            self.games[ctx.channel] = game = DiscordGame()
        
        await game.start(ctx, wait=True)
        del self.games[ctx.channel]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Check if channel has a game going
        game = self.games[message.channel]
        if game is None:
            return

        await game.check_message(message)


def setup(bot: BotBase):
    bot.add_cog(Boggle(bot))
