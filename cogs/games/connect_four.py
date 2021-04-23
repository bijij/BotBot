import asyncio
import random

import discord
from discord.ext import commands, menus

from donphan import Column, MaybeAcquire, SQLType, Table

from ditto import BotBase, Context
from ditto.utils.paginator import EmbedPaginator


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
COLUMNS = 7

BACKGROUND = "\N{BLACK CIRCLE FOR RECORD}\N{VARIATION SELECTOR-16}"
DISCS = ("\N{LARGE RED CIRCLE}", "\N{LARGE YELLOW CIRCLE}")

DIRECTIONS = ((1, 0), (0, 1), (1, -1), (1, 1))

K = 32  # Ranking K-factor


class Games(Table, schema="connect_four"):
    game_id: SQLType.Serial = Column(primary_key=True)
    players: list[SQLType.BigInt]
    winner: SQLType.SmallInt
    finished: SQLType.Boolean


class Ranking(Table, schema="connect_four"):
    user_id: SQLType.BigInt = Column(primary_key=True)
    ranking: SQLType.Integer = Column(default="1000")
    games: SQLType.Integer = Column(default="0")
    wins: SQLType.Integer = Column(default="0")
    losses: SQLType.Integer = Column(default="0")


class Board:
    def __init__(self, *, state: list[list[str]] = None, move: tuple[tuple[int, int], str] = None):
        self.columns = state or [[BACKGROUND for _ in range(ROWS)] for _ in range(COLUMNS)]

        if move is not None:
            (column, row), disc = move
            self.columns[column][row] = disc

        self.winner = None
        self.game_over = self.check_game_over()

    @property
    def state(self):
        state = " ".join(REGIONAL_INDICATOR_EMOJI)

        for row in range(ROWS):
            emoji = []
            for column in range(COLUMNS):
                emoji.append(self.columns[column][row])

            state = " ".join(emoji) + "\n" + state

        return state

    @property
    def legal_moves(self) -> list[int]:
        return [i for i, column in enumerate(self.columns) if column.count(BACKGROUND)]

    @classmethod
    def copy(cls, board, *, move=None):
        return cls(state=[[state for state in column] for column in board.columns], move=move)

    def check_game_over(self) -> bool:
        for column in range(COLUMNS):
            for row in range(ROWS):

                disc = self.columns[column][row]

                # Don't validate empty cells
                if disc == BACKGROUND:
                    continue

                # Check if last move was winning move
                counts = [0 for _ in range(4)]
                for i in range(-3, 4):

                    # Shortcut for last played disc
                    if i == 0:
                        for n in range(4):
                            counts[n] += 1
                    else:
                        # horizontal
                        if 0 <= column + i < COLUMNS:
                            if self.columns[column + i][row] == disc:
                                counts[0] += 1
                            else:
                                counts[0] = 0

                        if 0 <= row + i < ROWS:
                            # vertical
                            if self.columns[column][row + i] == disc:
                                counts[1] += 1
                            else:
                                counts[1] = 0

                            # descending
                            if 0 <= column + i < COLUMNS:
                                if self.columns[column + i][row + i] == disc:
                                    counts[2] += 1
                                else:
                                    counts[2] = 0

                            # ascending
                            if 0 <= column - i < COLUMNS:
                                if self.columns[column - i][row + i] == disc:
                                    counts[3] += 1
                                else:
                                    counts[3] = 0

                    for count in counts:
                        if count >= 4:
                            self.winner = DISCS.index(disc)
                            return True

        # No moves left draw
        return len(self.legal_moves) == 0

    def move(self, column: int, disc: str):
        row = self.columns[column].index(BACKGROUND)
        return Board.copy(self, move=((column, row), disc))


class AntiGravity(Board):
    @classmethod
    def flip(cls, board: Board) -> Board:

        state = []
        for column in board.columns:
            try:
                if isinstance(board, AntiGravity):
                    index = ROWS - column[::-1].index(BACKGROUND)
                else:
                    index = column.index(BACKGROUND)
            except ValueError:
                index = 0
            state.append(column[index:] + column[:index])

        return (Board if isinstance(board, AntiGravity) else AntiGravity)(state=state)

    def move(self, column: int, disc: str):
        row = ROWS - self.columns[column][::-1].index(BACKGROUND) - 1
        return AntiGravity.copy(self, move=((column, row), disc))


class Game(menus.Menu):
    ranked = True

    async def start(self, ctx, opponent, *, channel=None, wait=False):
        if random.random() < 0.5:
            self.players = (ctx.author, opponent)
        else:
            self.players = (opponent, ctx.author)

        for player in self.players:
            async with MaybeAcquire() as connection:
                await Ranking.insert(connection=connection, ignore_on_conflict=True, user_id=player.id)

        self.board = Board()
        self.current_player = 0

        # Setup buttons
        for emoji in REGIONAL_INDICATOR_EMOJI:
            self.add_button(menus.Button(emoji, self.place))

        await super().start(ctx, channel=channel, wait=wait)

    async def send_initial_message(self, ctx, channel):
        current_player = self.current_player
        return await channel.send(
            content=f"{self.players[current_player].mention}'s ({DISCS[current_player]}) turn!",
            embed=self.state,
        )

    def reaction_check(self, payload):
        if payload.message_id != self.message.id:
            return False

        current_player = self.current_player
        if payload.user_id != self.players[current_player].id:
            return False

        return payload.emoji in self.buttons

    @property
    def state(self):
        return discord.Embed(description=self.board.state)

    async def _end_game(self, resignation: int = None):
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
        async with MaybeAcquire() as connection:

            await Games.insert(
                connection=connection,
                players=[p.id for p in self.players],
                winner=winner,
                finished=resignation is None,
            )

            record_1 = await Ranking.fetchrow(connection=connection, user_id=self.players[0].id)
            record_2 = await Ranking.fetchrow(connection=connection, user_id=self.players[1].id)

            R1 = 10 ** (record_1["ranking"] / 400)
            R2 = 10 ** (record_2["ranking"] / 400)

            E1 = R1 / (R1 + R2)
            E2 = R2 / (R1 + R2)

            S1 = self.board.winner == 0 if self.board.winner is not None else 0.5
            S2 = self.board.winner == 1 if self.board.winner is not None else 0.5

            r1 = record_1["ranking"] + K * (S1 - E1)
            r2 = record_2["ranking"] + K * (S2 - E2)

            await Ranking.update_record(
                record_1,
                connection=connection,
                ranking=round(r1),
                games=record_1["games"] + 1,
                wins=record_1["wins"] + self.board.winner == 0,
                losses=record_1["losses"] + self.board.winner != 0,
            )

            await Ranking.update_record(
                record_2,
                connection=connection,
                ranking=round(r2),
                games=record_2["games"] + 1,
                wins=record_2["wins"] + self.board.winner == 1,
                losses=record_2["losses"] + self.board.winner != 1,
            )

    async def place(self, payload):
        column = REGIONAL_INDICATOR_EMOJI.index(str(payload.emoji))
        if column not in self.board.legal_moves:
            return ...

        self.board = self.board.move(column, DISCS[self.current_player])

        if self.board.game_over:
            return await self._end_game()

        self.current_player = not self.current_player
        await self.message.edit(
            content=f"{self.players[self.current_player].mention}'s ({DISCS[self.current_player]}) turn!",
            embed=self.state,
        )

    @menus.button("\N{BLACK SQUARE FOR STOP}\ufe0f", position=menus.Last(0))
    async def cancel(self, payload):
        await self._end_game(resignation=self.current_player)


class AntiGravityGame(Game):
    ranked = False

    async def place(self, payload):
        result = await super().place(payload)

        # Don't flip if not needed
        if result is Ellipsis or self.board.game_over:
            return

        if self.current_player == 0:  # and random.random() > 0.8:
            self.board = AntiGravity.flip(self.board)
            await self.message.edit(
                content=f"**Gravity Flip!**\n\n{self.players[self.current_player].mention}'s ({DISCS[self.current_player]}) turn!",
                embed=self.state,
            )

            if self.board.game_over:
                return await self._end_game()


class ConnectFour(commands.Cog):
    def __init__(self, bot: BotBase):
        self.bot = bot

    async def _get_opponent(self, ctx) -> discord.Member:
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
    async def c4(self, ctx: Context, *, opponent: discord.Member = None):
        """Start a Connect Four game!

        `opponent`: Another member of the server to play against. If not is set an open challenge is started.
        """
        if ctx.guild is None:
            raise commands.BadArgument("You must use this command in a guild.")

        if opponent is None:
            opponent = await self._get_opponent(ctx)
        else:
            if opponent.bot:
                raise commands.BadArgument("You cannot play against a bot yet")
            if opponent == ctx.author:
                raise commands.BadArgument("You cannot play against yourself.")

            if not await ctx.confirm(
                self.bot,
                f"{opponent.mention}, {ctx.author} has challenged you to Connect 4! do you accept?",
                opponent,
                channel=ctx.channel,
            ):
                opponent = None

        # If challenge timed out
        if opponent is None:
            raise commands.BadArgument("Challenge cancelled.")

        await Game().start(ctx, opponent, wait=True)

    @c4.command(invoke_without_command=True, name="flip", aliases=["antigravity"])
    # @commands.max_concurrency(1, per=commands.BucketType.channel)
    async def c4_flip(self, ctx: Context, *, opponent: discord.Member):
        """"""
        if ctx.guild is None:
            raise commands.BadArgument("You must use this command in a guild.")

        if opponent is None:
            opponent = await self._get_opponent(ctx)
        else:
            if opponent.bot:
                raise commands.BadArgument("You cannot play against a bot yet")
            if opponent == ctx.author:
                raise commands.BadArgument("You cannot play against yourself.")

            if not await ctx.confirm(
                self.bot,
                f"{opponent.mention}, {ctx.author} has challenged you to Connect 4! do you accept?",
                opponent,
                channel=ctx.channel,
            ):
                opponent = None

        # If challenge timed out
        if opponent is None:
            raise commands.BadArgument("Challenge cancelled.")

        await AntiGravityGame().start(ctx, opponent, wait=True)

    @c4.command(name="ranking", aliases=["elo"])
    async def c4_ranking(self, ctx: Context, *, player: discord.Member = None):
        """Get a player's ranking."""

        # Single player ranking
        if player is not None:
            record = await Ranking.fetchrow(user_id=player.id)

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

        embed = EmbedPaginator(title="Connect 4 Ranking", colour=discord.Colour.blue())

        for user_id, ranking, games, wins, losses in await Ranking.fetch(order_by="Ranking DESC"):
            user = self.bot.get_user(user_id) or "Unknown User"
            embed.add_field(
                name=f"{user} | {ranking}",
                value=f"Games: **{games}** | Wins: **{wins}** | Losses: **{losses}**",
            )

        await menus.MenuPages(embed).start(ctx)


def setup(bot: BotBase):
    bot.add_cog(ConnectFour(bot))
