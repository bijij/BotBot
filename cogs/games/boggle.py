import asyncio
import random

from collections import defaultdict
from functools import cached_property
from string import ascii_uppercase
from typing import List, NamedTuple, Set, Type

import discord
from discord.enums import NotificationLevel
from discord.ext import commands, menus
from discord.ext.commands.errors import BadArgument

from bot import BotBase, Context
from utils.tools import ordinal


ORIGINAL = 4
BIG = 5
SUPER_BIG = 6

# Diagram Emoji
AN_EMOJI = '<:_:808942978658861116>'
ER_EMOJI = '<:_:808944481382563870>'
HE_EMOJI = '<:_:808944480525746176>'
IN_EMOJI = '<:_:808942977464270849>'
QU_EMOJI = '<:_:806844322346565662>'
TH_EMOJI = '<:_:808944481264730112>'

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
    '\N{REGIONAL INDICATOR SYMBOL LETTER Q}',
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

DIAGRAMS = {
    '1': 'AN',
    '2': 'ER',
    '3': 'HE',
    '4': 'IN',
    '5': 'QU',
    '6': 'TH'
}

LETTERS_EMOJI = {
    '#': '\N{BLACK SQUARE FOR STOP}\ufe0f',
    '1': AN_EMOJI,
    '2': ER_EMOJI,
    '3': HE_EMOJI,
    '4': IN_EMOJI,
    '5': QU_EMOJI,
    '6': TH_EMOJI,
} | {letter: emoji for letter, emoji in zip(ascii_uppercase, REGIONAL_INDICATOR_EMOJI)}

DIE = {
    ORIGINAL: [
        'RIFOBX', 'IFEHEY', 'DENOWS', 'UTOKND',
        'HMSRAO', 'LUPETS', 'ACITOA', 'YLGKUE',
        '5BMJOA', 'EHISPN', 'VETIGN', 'BALIYT',
        'EZAVND', 'RALESC', 'UWILRG', 'PACEMD'
    ],
    BIG: [
        '5BZJXK', 'TOUOTO', 'OVWGR', 'AAAFSR', 'AUMEEG',
        'HHLRDO', 'MJDTHO', 'LHNROD', 'AFAISR', 'YIFASR',
        'TELPCI', 'SSNSEU', 'RIYPRH', 'DORDLN', 'CCWNST',
        'TTOTEM', 'SCTIEP', 'EANDNN', 'MNNEAG', 'UOTOWN',
        'AEAEEE', 'YIFPSR', 'EEEEMA', 'ITITIE', 'ETILIC'
    ],
    SUPER_BIG: [
        'AAAFRS', 'AAEEEE', 'AAEEOO', 'AAFIRS', 'ABDEIO', 'ADENNN',
        'AEEEEM', 'AEEGMU', 'AEGMNN', 'AEILMN', 'AEINOU', 'AFIRSY',
        '123456', 'BBJKXZ', 'CCENST', 'CDDLNN', 'CEIITT', 'CEIPST',
        'CFGNUY', 'DDHNOT', 'DHHLOR', 'DHHNOW', 'DHLNOR', 'EHILRS',
        'EIILST', 'EILPST', 'EIO###', 'EMTTTO', 'ENSSSU', 'GORRVW',
        'HIRSTV', 'HOPRST', 'IPRSYY', 'JK5WXZ', 'NOOTUW', 'OOOTTU',
    ]
}

with open('res/boggle.txt') as f:
    DICTIONARY = set(f.read().splitlines())

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

    def __init__(self, *, size=ORIGINAL, board=None):
        self.size = size

        if board is None:
            board = DIE[self.size].copy()
            random.shuffle(board)
            board = [[random.choice(board[row * self.size + column]) for column in range(self.size)] for row in range(self.size)]

        self.columns = board

    def board_contains(self, word: str, pos: Position = None, passed: List[Position] = []) -> bool:
        # Empty words
        if len(word) == 0:
            return True

        # When starting out
        if pos is None:

            # Check all positions
            for col in range(self.size):
                for row in range(self.size):
                    if self.board_contains(word, Position(col, row)):
                        return True

        # Checking new squares
        elif pos not in passed:
            # Check if letter matches current start of word
            letter = self.columns[pos.col][pos.row]
            if letter.isdigit():
                letter = DIAGRAMS[letter]

            if word[:len(letter)] == letter:

                # Check adjacent for next letter
                for x in range(-1, 2):
                    for y in range(-1, 2):

                        # don't check yourself
                        if x == 0 and y == 0:
                            continue

                        new_pos = Position(pos.col + x, pos.row + y)

                        # don't check out of bounds
                        if new_pos.col < 0 or new_pos.col >= self.size or new_pos.row < 0 or new_pos.row >= self.size:
                            continue

                        if self.board_contains(word[len(letter):], new_pos, [*passed, pos]):
                            return True

        # Otherwise cannot find word
        return False

    # @cached_property
    # def legal_words(self) -> Set[str]:
    #     return {word for word in DICTIONARY if self.is_legal(word)}

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
    name = 'Boggle'
    footer = None

    def __init__(self, *, size=ORIGINAL, **kwargs):
        self.board = Board(size=size)
        self.setup()
        super().__init__(**kwargs)

    @property
    def state(self):
        state = ''

        for row in range(self.board.size):
            emoji = []
            for column in range(self.board.size):
                emoji.append(LETTERS_EMOJI[self.board.columns[column][row]])

            state = ' '.join(emoji) + '\n' + state

        return discord.Embed(title=self.name, description=state).set_footer(text=self.footer)

    def setup(self):
        raise NotImplementedError

    async def send_initial_message(self, ctx, channel):
        return await channel.send(content='Boggle game started, you have 3 minutes!', embed=self.state)

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)
        # await self.bot.loop.run_in_executor(None, lambda: self.board.legal_words)

    async def finalize(self, timed_out):
        self.bot.dispatch('boggle_game_complete', self.message.channel)

    def get_points(self, words: List[str]) -> int:
        return self.board.total_points(words)

    def check_word(self, word: str) -> bool:
        return self.board.is_legal(word)

    async def check_message(self, message: discord.Message):
        raise NotImplementedError

    @menus.button('\N{BLACK SQUARE FOR STOP}\ufe0f', position=menus.Last(0))
    async def cancel(self, payload):
        await self.message.edit(content='Game Cancelled.')
        self.stop()


class ShuffflingGame(Game):

    def __init__(self, *, size=ORIGINAL, **kwargs):
        super().__init__(size=size, **kwargs)
        self.boards = [self.board]

    def shuffle(self):
        raise NotImplementedError

    async def shuffle_task(self):
        for i in range(5):
            await asyncio.sleep(30)
            if not self._running:
                return

            # Shuffle board
            self.shuffle()
            self.boards.append(self.board)

            # Note Board Updated
            await self.message.channel.send('Board Updated!')

            # Update Board Message
            time = ["2 minutes, 30 seconds", '2 minutes', '1 minute, 30 seconds', '1 minute', '30 seconds'][i]
            await self.message.edit(content=f'Board Updated! You have {time} left!', embed=self.state)

    async def start(self, *args, **kwargs):
        await super().start(*args, **kwargs)
        self.bot.loop.create_task(self.shuffle_task())

    def get_points(self, words: List[str]) -> int:
        points = 0
        for word in words:
            for board in self.boards:
                pts = board.points(word)
                if pts:
                    points += pts
                    break

        return points


class DiscordGame(Game):
    name = 'Discord Boggle'
    footer = 'First to find a word wins points!'

    @property
    def scores(self):
        embed = discord.Embed()

        i = 0
        old = None

        for user, words in sorted(self.words.items(), key=lambda v: self.get_points(v[1]), reverse=True):
            points = self.get_points(words)

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

        if not self.check_word(word):
            return

        if word in self.all_words:
            return

        # Add to user words
        self.all_words.add(word)
        self.words[message.author].add(word)

        await message.add_reaction('\N{WHITE HEAVY CHECK MARK}')

    async def finalize(self, timed_out: bool):
        await super().finalize(timed_out)
        if timed_out:
            await self.message.edit(content='Game Over!')
            await self.message.reply(embed=self.scores)


class ClassicGame(Game):
    name = 'Classic Boggle'
    footer = 'Keep a list of words til the end!'

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

                if not self.check_word(word):
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
        await super().finalize(timed_out)

        if timed_out:
            await self.message.edit(content='Game Over!')
            await self.message.reply('Game Over! you have 10 seconds to send in your words.')
            self.over = True
            await asyncio.sleep(10)
            self.filter_lists()
            await self.message.reply(embed=self.scores)


class FlipGame(ShuffflingGame, DiscordGame):
    name = 'Flip Boggle'
    footer = 'Find words as fast as you can, rows will flip positions every 30 seconds.'

    def shuffle(self):
        rows = [[self.board.columns[x][y] for x in range(self.board.size)] for y in range(self.board.size)]
        random.shuffle(rows)
        self.board = Board(size=self.board.size, board=[[rows[x][y] for x in range(self.board.size)] for y in range(self.board.size)])


class BoggleGame(ShuffflingGame, DiscordGame):
    name = 'Boggle Boggle'
    footer = 'Find words as fast as you can, letters will shuffle positions every 30 seconds.'

    def shuffle(self):
        letters = [self.board.columns[y][x] for x in range(self.board.size) for y in range(self.board.size)]
        random.shuffle(letters)
        self.board = Board(size=self.board.size, board=[letters[x * self.board.size:x * self.board.size + self.board.size] for x in range(self.board.size)])


class Boggle(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot
        self.games = defaultdict(lambda: None)

    def _get_game_type(self, ctx: Context) -> Type[Game]:
        if ctx.invoked_subcommand is None:
            return DiscordGame
        elif ctx.invoked_subcommand is self.boggle_classic:
            return ClassicGame
        elif ctx.invoked_subcommand is self.boggle_flip:
            return FlipGame
        elif ctx.invoked_subcommand is self.boggle_boggle:
            return BoggleGame
        raise BadArgument('Unknown boggle game type')

    def _check_size(self, ctx: Context) -> int:
        if ctx.prefix.upper().endswith('SUPER BIG '):
            return SUPER_BIG
        elif ctx.prefix.upper().endswith('BIG '):
            return BIG
        return ORIGINAL

    @commands.group()
    @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def boggle(self, ctx: Context):
        """Start's a game of Boggle.

        The board size can be set by command prefix.
        e.g. `(bb)big boggle` will result in a 5x5 board.

        Players have 3 minutes to find as many words as they can, the first person to find
        a word gets the points.
        """
        game_type = self._get_game_type(ctx)
        self.games[ctx.channel] = game = game_type(size=self._check_size(ctx))
        await game.start(ctx, wait=False)

        def check(channel):
            return channel.id == ctx.channel.id

        channel = await self.bot.wait_for('boggle_game_complete', check=check, timeout=200)
        del self.games[channel]

    @boggle.command(name='classic')
    async def boggle_classic(self, ctx: Context):
        """Start's a cassic game of boggle.

        Players will write down as many words as they can and send after 3 minutes has passed.
        Points are awarded to players with unique words.
        """
        ...

    @boggle.command(name='flip')
    async def boggle_flip(self, ctx: Context):
        """Start's a cassic game of boggle.

        Rows will randomly shuffle every 30s.
        The first person to finda word gets the points.
        """
        ...

    @boggle.command(name='boggle')
    async def boggle_boggle(self, ctx: Context):
        """Start's a cassic game of boggle.

        All letters will randomly shuffle flip every 30s.
        The first person to finda word gets the points.
        """
        ...

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Check if channel has a game going
        game = self.games[message.channel]
        if game is None:
            return

        await game.check_message(message)


def setup(bot: BotBase):
    bot.add_cog(Boggle(bot))
