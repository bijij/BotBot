from __future__ import annotations

import asyncio
import random
from functools import cached_property
from typing import Iterator, Literal, Optional, Union, overload

import discord
from discord.ext import commands
from discord.utils import MISSING
from ditto import BotBase, Cog, Context
from ditto.types import User
from ditto.utils.message import confirm

BoardState = list[list[Optional[bool]]]


STATES = (
    "\N{REGIONAL INDICATOR SYMBOL LETTER O}",
    "\N{REGIONAL INDICATOR SYMBOL LETTER X}",
)


class Board:
    def __init__(
        self,
        state: BoardState,
        current_player: bool = False,
        last_move: Optional[tuple[int, int]] = None,
    ) -> None:
        self.state = state
        self.current_player = current_player
        self.last_move = last_move
        self.winner: Optional[bool] = MISSING

    @property
    def legal_moves(self) -> Iterator[tuple[int, int]]:
        for c in range(3):
            for r in range(3):
                if self.state[r][c] is None:
                    yield (r, c)

    @cached_property
    def over(self) -> bool:

        # vertical
        for c in range(3):
            token = self.state[0][c]
            if token is None:
                continue
            if self.state[1][c] == token and self.state[2][c] == token:
                self.winner = token
                return True

        # horizontal
        for r in range(3):
            token = self.state[r][0]
            if token is None:
                continue
            if self.state[r][1] == token and self.state[r][2] == token:
                self.winner = token
                return True

        # descending diag
        if self.state[0][0] is not None:
            token = self.state[0][0]
            if self.state[1][1] == token and self.state[2][2] == token:
                self.winner = token
                return True

        # ascending diag
        if self.state[0][2] is not None:
            token = self.state[0][2]
            if self.state[1][1] == token and self.state[2][0] == token:
                self.winner = token
                return True

        # Check if board is empty
        for _ in self.legal_moves:
            break
        else:
            self.winner = None
            return True

        return False

    def move(self, r: int, c: int) -> Board:
        if (r, c) not in self.legal_moves:
            raise ValueError("Illegal Move")

        new_state = [[self.state[r][c] for c in range(3)] for r in range(3)]
        new_state[r][c] = self.current_player

        return Board(new_state, not self.current_player, (r, c))

    @classmethod
    def new_game(cls) -> Board:
        state: BoardState = [[None for _ in range(3)] for _ in range(3)]
        return cls(state)


class AI:
    def __init__(self, player: bool) -> None:
        self.player = player

    def move(self, game: Board) -> Board:
        column = random.choice(tuple(game.legal_moves))
        return game.move(*column)


class NegamaxAI(AI):
    def __init__(self, player: bool) -> None:
        super().__init__(player)

    def heuristic(self, game: Board, sign: int) -> float:
        if sign == -1:
            player = not self.player
        else:
            player = self.player

        if game.over:
            if game.winner is None:
                return 0
            if game.winner == player:
                return 1_000_000
            return -1_000_000

        return random.randint(-10, 10)

    @overload
    def negamax(
        self,
        game: Board,
        depth: Literal[0] = ...,
        alpha: float = ...,
        beta: float = ...,
        sign: int = ...,
    ) -> tuple[int, int]:
        ...

    @overload
    def negamax(
        self,
        game: Board,
        depth: int = ...,
        alpha: float = ...,
        beta: float = ...,
        sign: int = ...,
    ) -> float:
        ...

    def negamax(
        self,
        game: Board,
        depth: int = 0,
        alpha: float = float("-inf"),
        beta: float = float("inf"),
        sign: int = 1,
    ) -> Union[float, tuple[int, int]]:
        if game.over:
            return sign * self.heuristic(game, sign)

        move = MISSING

        score = float("-inf")
        for c in game.legal_moves:
            move_score = -self.negamax(game.move(*c), depth + 1, -beta, -alpha, -sign)

            if move_score > score:
                score = move_score
                move = c

            alpha = max(alpha, score)
            if alpha >= beta:
                break

        if depth == 0:
            return move
        else:
            return score

    def move(self, game: Board) -> Board:
        return game.move(*self.negamax(game))


class Button(discord.ui.Button["Game"]):
    def __init__(self, r: int, c: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", group=c)
        self.r = r
        self.c = c

    def click(self):
        if self.view.board.current_player:
            self.style = discord.ButtonStyle.danger
            self.label = "X"
        else:
            self.style = discord.ButtonStyle.success
            self.label = "O"

        self.disabled = True

        self.view.board = self.view.board.move(self.r, self.c)

    async def move(self, interaction: discord.Interaction):
        self.click()
        content = f"{self.view.current_player.mention}'s' ({STATES[self.view.board.current_player]}) turn!"

        if self.view.board.over:
            if self.view.board.winner is not None:
                content = (
                    f"{self.view.players[self.view.board.winner].mention} ({STATES[self.view.board.winner]}) wins!"
                )
            else:
                content = "Draw!"

            for child in self.view.children:
                child.disabled = True  # type: ignore

            self.view.stop()

        if not self.view.board.over and self.view.current_player.bot:
            r, c = self.view.make_ai_move()

            for child in self.view.children:
                if child.r == r and child.c == c:  # type: ignore
                    await child.move(interaction)  # type: ignore
                    break
        else:
            await interaction.response.edit_message(content=content, view=self.view)

    async def callback(self, interaction: discord.Interaction):
        await self.move(interaction)


class Game(discord.ui.View):
    def __init__(self, players: tuple[User, User]):
        self.players = list(players)
        random.shuffle(self.players)

        super().__init__()
        self.board = Board.new_game()

        for r in range(3):
            for c in range(3):
                self.add_item(Button(r, c))

        if self.current_player.bot:
            r, c = self.make_ai_move()

            for child in self.children:
                if child.r == r and child.c == c:  # type: ignore
                    child.click()  # type: ignore
                    break

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.current_player:
            await interaction.response.send_message('Sorry, you are not playing', ephemeral=True)
            return False
        return True

    def make_ai_move(self) -> tuple[int, int]:
        ai = NegamaxAI(self.board.current_player)
        return ai.move(self.board).last_move  # type: ignore

    @property
    def current_player(self) -> User:
        return self.players[self.board.current_player]


class TicTacToe(Cog):
    async def _get_opponent(self, ctx: Context) -> Optional[discord.Member]:
        message = await ctx.channel.send(
            embed=discord.Embed(description=f"{ctx.author.mention} wants to play Tic-Tac-Toe.").set_footer(
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
            _, opponent = await self.bot.wait_for("reaction_add", check=check, timeout=60)
            return opponent
        except asyncio.TimeoutError:
            pass
        finally:
            await message.delete()
        return None

    @commands.command(aliases=["tic", "tic_tac_toe"])
    # @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def tictactoe(self, ctx: Context, *, opponent: Optional[discord.Member] = None):
        """Start a Tic-Tac-Toe game!

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
                if not await confirm(
                    self.bot,
                    ctx.channel,
                    opponent,
                    f"{opponent.mention}, {ctx.author} has challenged you to Tic-Tac-Toe! do you accept?",
                ):
                    opponent = None

        # If challenge timed out
        if opponent is None:
            raise commands.BadArgument("Challenge cancelled.")

        game = Game((ctx.author, opponent))

        await ctx.send(f"{game.current_player.mention}'s (X) turn!", view=game)  # type: ignore


def setup(bot: BotBase) -> None:
    bot.add_cog(TicTacToe(bot))
