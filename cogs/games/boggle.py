from collections import defaultdict
import random
import re
from string import ascii_uppercase
from typing import List, NamedTuple

import discord
from discord.ext import commands, menus

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

                    if 0 <= new_col < COLUMNS and 0 <= new_row < ROWS:
                        if self.board_contains(word[1 if word[0] != 'Q' else 2:], Position(new_col, new_row), [*passed, pos]):
                            return True

        # Otherwise cannot find word
        return False

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

        self.all_words = set()
        self.words = defaultdict(set)

        super().__init__(**kwargs)

    def check_word(self, word: str, user: discord.User) -> bool:
        if not self.board.is_legal(word):
            return False

        if word in self.all_words:
            return False
        
        # Add to user words
        self.all_words.add(word)
        self.words[user].add(word)

        return True

    async def send_initial_message(self, ctx, channel):
        return await channel.send(content="Boggle game started, you have 3 minutes!", embed=self.state)

    @property
    def state(self):
        state = ''

        for row in range(ROWS):
            emoji = []
            for column in range(COLUMNS):
                emoji.append(LETTERS_EMOJI[self.board.columns[column][row]])

            state = ' '.join(emoji) + '\n' + state

        return discord.Embed(description=state)

    @property
    def leaderboard(self):
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

    async def finalize(self, timed_out: bool):
        if not timed_out:
            return
        await self.message.edit(content='Game Over!')
        await self.message.reply(embed=self.leaderboard)

    @menus.button('\N{BLACK SQUARE FOR STOP}\ufe0f', position=menus.Last(0))
    async def cancel(self, payload):
        await self.message.edit(content='Game Cancelled.')
        self.stop()


class Boggle(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot
        self.games = defaultdict(lambda: None)

    @commands.command()
    @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def boggle(self, ctx: Context):
        """Start a game of boggle."""
        self.games[ctx.channel] = game = Game()
        await game.start(ctx, wait=True)
        del self.games[ctx.channel]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Check if channel has a game going
        game = self.games[message.channel]
        if game is None:
            return
        
        # Check message is single word
        if not message.content.isalpha():
            return

        if game.check_word(message.content, message.author):
            try:
                await message.add_reaction('\N{WHITE HEAVY CHECK MARK}')
            except discord.HTTPException:
                ...

def setup(bot: BotBase):
    bot.add_cog(Boggle(bot))
