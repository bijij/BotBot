from __future__ import annotations

import asyncio
import copy
from functools import cache, cached_property, partial
import random
from collections.abc import Iterator
from typing import Literal, Optional, TypeVar, Union, overload

import discord
from discord.ext import commands, menus
from discord.utils import MISSING
from ditto import BotBase, Cog, Context
from ditto.utils.paginator import EmbedPaginator
from donphan import Column, SQLType, Table

REGIONAL_INDICATOR_EMOJI = (
    "\N{REGIONAL INDICATOR SYMBOL LETTER A}",
    "\N{REGIONAL INDICATOR SYMBOL LETTER B}",
    "\N{REGIONAL INDICATOR SYMBOL LETTER C}",
    "\N{REGIONAL INDICATOR SYMBOL LETTER D}",
    "\N{REGIONAL INDICATOR SYMBOL LETTER E}",
    "\N{REGIONAL INDICATOR SYMBOL LETTER F}",
    "\N{REGIONAL INDICATOR SYMBOL LETTER G}",
)

ROWS = 6
COLS = 7

MIN_DEPTH = 3
MAX_DEPTH = 5

BACKGROUND = "\N{BLACK CIRCLE FOR RECORD}\N{VARIATION SELECTOR-16}"
DISCS = ("\N{LARGE RED CIRCLE}", "\N{LARGE YELLOW CIRCLE}")

K = 32  # Ranking K-factor

B = TypeVar("B", bound="Board")
AG = TypeVar("AG", bound="AntiGravity")

BoardState = list[list[Optional[bool]]]


class Games(Table, schema="connect_four"):
    game_id: Column[SQLType.Serial] = Column(primary_key=True)
    players: Column[list[SQLType.BigInt]]
    winner: Column[SQLType.SmallInt]
    finished: Column[SQLType.Boolean]


class Ranking(Table, schema="connect_four"):
    user_id: Column[SQLType.BigInt] = Column(primary_key=True)
    ranking: Column[SQLType.Integer] = Column(default="1000")
    games: Column[SQLType.Integer] = Column(default="0")
    wins: Column[SQLType.Integer] = Column(default="0")
    losses: Column[SQLType.Integer] = Column(default="0")


class Board:
    def __init__(
        self,
        state: BoardState,
        current_player: bool = MISSING,
        last_move: Optional[tuple[int, int]] = None,
    ) -> None:
        self.state = state
        if current_player is MISSING:
            self.current_player = random.choice((True, False))
        else:
            self.current_player = current_player
        self.last_move = last_move
        self.winner: Optional[bool] = MISSING

    @property
    def display(self):
        ...

    @property
    def legal_moves(self) -> Iterator[int]:
        for c in range(COLS):
            for r in range(ROWS):
                if self.state[r][c] is None:
                    yield c
                    break

    def move(self, column: int, cls: type[B] = MISSING, *, flipped: bool = False) -> B:
        if column not in self.legal_moves:
            raise ValueError("Illegal Move")

        new_state = [[self.state[r][c] for c in range(COLS)] for r in range(ROWS)]

        iterator = range(ROWS)
        if not flipped:
            iterator = reversed(iterator)

        for r in iterator:
            if new_state[r][column] is None:
                new_state[r][column] = self.current_player
                break

        if cls is MISSING:
            cls = self.__class__  # type: ignore

        return cls(new_state, not self.current_player, (r, column))  # type: ignore

    @cache
    def in_a_row(self, n: int, position: tuple[int, int]) -> bool:

        r, c = position
        token = self.state[r][c]

        counts = [0 for _ in range(4)]  # 4 directions

        for o in range(-(n - 1), n):

            # horizontal
            if 0 <= c + o < COLS:
                if self.state[r][c + o] == token:
                    counts[0] += 1
                else:
                    counts[0] = 0

            # vertical
            if 0 <= r + o < ROWS:
                if self.state[r + o][c] == token:
                    counts[1] += 1
                else:
                    counts[1] = 0

                # asc diag
                if 0 <= c + o < COLS:
                    if self.state[r + o][c + o] == token:
                        counts[2] += 1
                    else:
                        counts[2] = 0

                # desc diag
                if 0 <= c - o < COLS:
                    if self.state[r + o][c - o] == token:
                        counts[3] += 1
                    else:
                        counts[3] = 0

            if any(c >= n for c in counts):
                return True

        return False

    @cached_property
    def over(self) -> bool:

        if self.last_move is None:
            return False

        if self.winner is not MISSING:
            return True

        for _ in self.legal_moves:
            break
        else:
            self.winner = None
            return True

        for c in range(COLS):
            for r in range(ROWS):
                token = self.state[r][c]
                if token is None:
                    continue

                if self.in_a_row(4, (r, c)):
                    self.winner = token
                    return True

        return False

    @classmethod
    def new_game(cls: type[B]) -> B:
        state = [[None for _ in range(COLS)] for _ in range(ROWS)]
        return cls(state, False)  # type: ignore


class AntiGravity(Board):
    def flip(self: AG) -> AG:

        state = [[None for _ in range(COLS)] for _ in range(ROWS)]

        for c in range(COLS):
            for r in range(ROWS):
                state[-r - 1][c] = self.state[r][c]  # type: ignore

        if isinstance(self, Flipped):
            cls = AntiGravity
        else:
            cls = Flipped

        return cls(state, self.current_player)  # type: ignore

    def move(self, column: int, *, cls: type[AG] = MISSING, flipped: bool = False) -> AG:
        board = super().move(column, cls=cls, flipped=flipped)

        if board.over:
            return board

        if self.current_player:
            board = board.flip()

        return board


class Flipped(AntiGravity):
    def move(self, column: int, *, cls: type[AG] = MISSING, flipped: bool = True) -> AG:
        return super().move(column, cls=cls, flipped=flipped)


class AI:
    def __init__(self, player: bool, depth: int) -> None:
        self.player = player
        self.max_depth = depth

    def heuristic(self, game: Board, depth: int) -> float:
        if game.over:
            if game.winner is None:
                return 0
            elif game.winner == self.player:
                return 100 / depth
            else:
                return -100 / depth

        score = 0
        for r in range(ROWS):
            for c in range(COLS):
                token = game.state[r][c]
                if token != None:
                    if game.in_a_row(3, (r, c)):
                        if token == self.player:
                            score += 2.5 / depth
                        else:
                            score -= 2.5 / depth

        return score

    @overload
    def minimax(
        self,
        game: Board,
        depth: Literal[0] = ...,
        alpha: float = ...,
        beta: float = ...,
        is_maximising: bool = ...,
    ) -> int:
        ...

    @overload
    def minimax(
        self,
        game: Board,
        depth: int = ...,
        alpha: float = ...,
        beta: float = ...,
        is_maximising: bool = ...,
    ) -> float:
        ...

    def minimax(
        self,
        game: Board,
        depth: int = 0,
        alpha: float = float("-inf"),
        beta: float = float("inf"),
        is_maximising: bool = True,
    ) -> Union[float, int]:
        if depth == self.max_depth or game.over:
            return self.heuristic(game, depth)

        moves = []
        scores = {}

        if is_maximising:
            score = float("-inf")

            for c in game.legal_moves:
                move_score = self.minimax(game.move(c), depth + 1, alpha, beta, False)

                scores[c] = move_score
                if move_score > score:
                    score = move_score
                    moves = [c]
                elif move_score == score:
                    moves.append(c)

                alpha = max(alpha, score)
                if alpha >= beta:
                    break
        else:
            score = float("inf")
            for c in game.legal_moves:
                score = min(score, self.minimax(game.move(c), depth + 1, alpha, beta, True))

                beta = min(beta, score)
                if alpha >= beta:
                    break

        if depth == 0:
            return random.choice(moves)
        else:
            return score

    def move(self, game: B) -> B:
        return game.move(self.minimax(game))


class Game(menus.Menu):
    async def start(self, ctx, opponent, *, channel=None, wait=False, ranked: bool = True, cls: type[Board] = Board):
        self.players = (ctx.author, opponent)
        self.ranked = ranked

        if self.ranked:
            for player in self.players:
                async with ctx.db as connection:
                    await Ranking.insert(connection, ignore_on_conflict=True, user_id=player.id)

        self.board = cls.new_game()

        if self.players[self.board.current_player].bot:
            await self._ai_turn()

        # Setup buttons
        for emoji in REGIONAL_INDICATOR_EMOJI:
            self.add_button(menus.Button(emoji, self.place))

        await super().start(ctx, channel=channel, wait=wait)

    async def send_initial_message(self, ctx, channel):
        return await channel.send(
            content=f"{self.players[self.board.current_player].mention}'s ({DISCS[self.board.current_player]}) turn!",
            embed=self.state,
        )

    def reaction_check(self, payload):
        if payload.message_id != self.message.id:
            return False

        if payload.user_id == self.bot.user.id:
            return False

        if payload.user_id != self.players[self.board.current_player].id:
            return False

        return payload.emoji in self.buttons

    @property
    def state(self):
        state = ""
        for r in range(ROWS):
            emoji = []
            for c in range(COLS):
                token = self.board.state[r][c]
                if token is None:
                    emoji.append(BACKGROUND)
                else:
                    emoji.append(DISCS[token])

            state += "\n" + " ".join(emoji)

        state += "\n" + " ".join(REGIONAL_INDICATOR_EMOJI)

        return discord.Embed(description=state)

    async def _ai_turn(self):
        delta = MAX_DEPTH - MIN_DEPTH
        depth = self.players[self.board.current_player].id % delta + MAX_DEPTH + 1
        ai = AI(self.board.current_player, depth)
        move_call = partial(ai.move, self.board)
        self.board = await self.bot.loop.run_in_executor(None, move_call)

    async def _next_turn(self):
        if self.board.over:
            return await self._end_game()

        await self.message.edit(
            content=f"{self.players[self.board.current_player].mention}'s ({DISCS[self.board.current_player]}) turn!",
            embed=self.state,
        )

        # if AI auto play turn
        if self.players[self.board.current_player].bot:
            await self._ai_turn()
            await self._next_turn()

    async def _end_game(self, resignation: int = None):
        winner: Optional[int]

        if resignation is not None:
            winner = not resignation
            content = f"Game cancelled by {self.players[resignation].mention} ({DISCS[resignation]})!"
        elif self.board.winner is not None:
            winner = self.board.winner
            content = f"{self.players[self.board.winner].mention} ({DISCS[self.board.winner]})  Wins!"
        else:
            winner = None
            content = "Draw!"

        await self.message.edit(content=f"Game Over! {content}", embed=self.state)
        self.stop()

        if not self.ranked:
            return

        # Calulate new ELO
        async with self.ctx.db as connection:

            await Games.insert(
                connection,
                players=[p.id for p in self.players],
                winner=winner,
                finished=resignation is None,
            )

            record_1 = await Ranking.fetch_row(connection, user_id=self.players[0].id)
            record_2 = await Ranking.fetch_row(connection, user_id=self.players[1].id)

            R1 = 10 ** (record_1["ranking"] / 400)
            R2 = 10 ** (record_2["ranking"] / 400)

            E1 = R1 / (R1 + R2)
            E2 = R2 / (R1 + R2)

            S1 = (self.board.winner == 0) if self.board.winner is not None else 0.5
            S2 = (self.board.winner == 1) if self.board.winner is not None else 0.5

            r1 = record_1["ranking"] + K * (S1 - E1)
            r2 = record_2["ranking"] + K * (S2 - E2)

            await Ranking.update_record(
                connection,
                record_1,
                ranking=round(r1),
                games=record_1["games"] + 1,
                wins=record_1["wins"] + self.board.winner == 0,
                losses=record_1["losses"] + self.board.winner != 0,
            )

            await Ranking.update_record(
                connection,
                record_2,
                ranking=round(r2),
                games=record_2["games"] + 1,
                wins=record_2["wins"] + self.board.winner == 1,
                losses=record_2["losses"] + self.board.winner != 1,
            )

    async def place(self, payload):
        column = REGIONAL_INDICATOR_EMOJI.index(str(payload.emoji))
        if column not in self.board.legal_moves:
            return ...

        self.board = self.board.move(column)
        await self._next_turn()

    @menus.button("\N{BLACK SQUARE FOR STOP}\ufe0f", position=menus.Last(0))
    async def cancel(self, payload):
        await self._end_game(resignation=self.board.current_player)


class ConnectFour(Cog):
    def __init__(self, bot: BotBase):
        self.bot = bot

    async def _get_opponent(self, ctx: Context) -> Optional[discord.Member]:
        message = await ctx.channel.send(
            embed=discord.Embed(description=f"{ctx.author.mention} wants to play Connect Four.").set_footer(
                text="react with \N{WHITE HEAVY CHECK MARK} to accept the challenge."
            )
        )
        await message.add_reaction("\N{WHITE HEAVY CHECK MARK}")

        def check(reaction, user):
            if reaction.emoji != "\N{WHITE HEAVY CHECK MARK}":
                return False
            if user.bot:
                return False
            if user == ctx.author:
                return False
            return True

        try:
            _, opponent = await self.bot.wait_for("reaction_add", check=check)
            return opponent
        except asyncio.TimeoutError:
            pass
        finally:
            await message.delete()
        return None

    @commands.group(invoke_without_command=True)
    # @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def c4(self, ctx: Context, *, opponent: Optional[discord.Member] = None):
        """Start a Connect Four game!

        `opponent`: Another member of the server to play against. If not is set an open challenge is started.
        """
        if ctx.guild is None:
            raise commands.BadArgument("You must use this command in a guild.")

        if opponent is None:
            opponent = await self._get_opponent(ctx)
        else:
            if opponent == ctx.author:
                raise commands.BadArgument("You cannot play against yourself.")

            if not opponent.bot:
                _ctx = copy.copy(ctx)
                _ctx.author = opponent

                if not await _ctx.confirm(
                    f"{opponent.mention}, {ctx.author} has challenged you to Connect 4! do you accept?",
                ):
                    opponent = None

        # If challenge timed out
        if opponent is None:
            raise commands.BadArgument("Challenge cancelled.")

        await Game().start(ctx, opponent, wait=True, ranked=not opponent.bot)

    @c4.command(invoke_without_command=True, name="flip", aliases=["antigravity"])
    # @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def c4_flip(self, ctx: Context, *, opponent: Optional[discord.Member] = None):
        """ """
        if ctx.guild is None:
            raise commands.BadArgument("You must use this command in a guild.")

        if opponent is None:
            opponent = await self._get_opponent(ctx)
        else:
            if opponent == ctx.author:
                raise commands.BadArgument("You cannot play against yourself.")

            if not opponent.bot:
                _ctx = copy.copy(ctx)
                _ctx.author = opponent

                if not await _ctx.confirm(
                    f"{opponent.mention}, {ctx.author} has challenged you to Connect 4! do you accept?",
                ):
                    opponent = None

        # If challenge timed out
        if opponent is None:
            raise commands.BadArgument("Challenge cancelled.")

        await Game().start(ctx, opponent, wait=True, ranked=False, cls=AntiGravity)

    @c4.command(name="ranking", aliases=["elo"])
    async def c4_ranking(self, ctx: Context, *, player: Optional[discord.Member] = None):
        """Get a player's ranking."""

        async with ctx.db as connection:

            # Single player ranking
            if player is not None:
                record = await Ranking.fetch_row(connection, user_id=player.id)

                if record is None:
                    raise commands.BadArgument(f"{player.mention} does not have a ranking.")

                user_id, ranking, games, wins, losses = record

                embed = (
                    discord.Embed(title=f"{player}'s Ranking:")
                    .add_field(name="Ranking", value=ranking)
                    .add_field(name="Games Played", value=f"**{games}**")
                    .add_field(name="Wins", value=f"**{wins}** ({wins/games:.0%})")
                    .add_field(name="Losses", value=f"**{losses}** ({losses/games:.0%})")
                )

                return await ctx.send(embed=embed)

            embed = EmbedPaginator(title="Connect 4 Ranking", colour=discord.Colour.blue(), max_fields=12)

            for user_id, ranking, games, wins, losses in await Ranking.fetch(
                connection, order_by=(Ranking.ranking, "DESC")
            ):
                if games == 0:
                    continue
                user = self.bot.get_user(user_id) or "Unknown User"
                embed.add_field(
                    name=f"{user} | {ranking}",
                    value=f"Games: **{games}** | Wins: **{wins}** | Losses: **{losses}**",
                )

        await menus.MenuPages(embed, delete_message_after=True).start(ctx)


def setup(bot: BotBase):
    bot.add_cog(ConnectFour(bot))
