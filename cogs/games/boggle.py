import random
from string import ascii_uppercase

import discord
from discord.ext import commands, menus

from bot import BotBase, Context


QU_EMOJI = '<:_:806844322346565662>'

ROWS = 4
COLUMNS = 4


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


LETTERS_EMOJI = {letter: emoji for letter, emoji in zip(ascii_uppercase, REGIONAL_INDICATOR_EMOJI)}

DIE = [
    ["RIFOBX", "IFEHEY", "DENOWS", "UTOKND"],
    ["HMSRAO", "LUPETS", "ACITOA", "YLGKUE"],
    ["QBMJOA", "EHISPN", "VETIGN", "BALIYT"],
    ["EZAVND", "RALESC", "UWILRG", "PACEMD"]
]


class Board:

    def __init__(self):
        self.columns = [[LETTERS_EMOJI[random.choice(die)] for die in row] for row in DIE]


class Game(menus.Menu):
    async def send_initial_message(self, ctx, channel):
        return await channel.send(embed=self.state)

    @property
    def state(self):
        state = ''

        for row in range(ROWS):
            emoji = []
            for column in range(COLUMNS):
                emoji.append(self.board.columns[column][row])

            state = ' '.join(emoji) + '\n' + state

        return discord.Embed(description=state)

    async def start(self, ctx: Context, *, channel=None, wait=False):
        self.board = Board()
        await super().start(ctx, channel=channel, wait=wait)
        self.stop()


class Boggle(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

    @commands.command()
    # @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def boggle(self, ctx: Context):
        await Game().start(ctx, wait=True)


def setup(bot: BotBase):
    bot.add_cog(Boggle(bot))
