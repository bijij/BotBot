from random import sample
import discord

from discord.ext import boardgames, commands

from ditto import Cog, Context


class Cell:
    def __init__(self, board, y: int, x: int):
        self.board = board
        self.y = y
        self.x = x
        self.mine = False
        self.clicked = False
        self.flagged = False

    @property
    def number(self):
        count = 0
        for y in range(self.y - 1, self.y + 2):
            for x in range(self.x - 1, self.x + 2):
                if 0 <= y < self.board.size_y and 0 <= x < self.board.size_x and self.board[x, y].mine:
                    count += 1
        return count

    def __str__(self):
        if self.clicked:

            if self.number == 0:
                number = "\u200b"
            else:
                number = boardgames.keycap_digit(self.number)

            return "💥" if self.mine else number
        else:
            return "🚩" if self.flagged else "⬜"


class Game(boardgames.Board[Cell]):
    def __init__(self, size_x=10, size_y=7):
        super().__init__(size_x, size_y)
        self.record = None
        self.last_state = None

        self._state = [[Cell(self, y, x) for x in range(self.size_x)] for y in range(self.size_y)]

    def setup(self, click_y: int, click_x: int):
        """Places mines on the board"""
        cells = [(i // self.size_x, i % self.size_x) for i in range(self.size_x * self.size_y)]
        cells.remove((click_y, click_x))

        for y, x in sample(cells, max(int((self.size_y * self.size_x) // (6 + 2 / 4)), 5)):
            self[x, y].mine = True

    @property
    def num_mines(self) -> int:
        """Returns the number of mines"""
        count = 0
        for row in self:
            for cell in row:
                if cell.mine:
                    count += 1
        return count

    @property
    def num_flags(self) -> int:
        """Returns the currently placed number of flags"""
        count = 0
        for row in self:
            for cell in row:
                if cell.flagged:
                    count += 1
        return count

    @property
    def lost(self) -> bool:
        """Returns wether the game was lost or not."""
        for row in self:
            for cell in row:
                if cell.mine and cell.clicked:
                    return True
        return False

    @property
    def solved(self) -> bool:
        """Returns wether the board has been solved"""
        count = 0
        for row in self:
            for cell in row:
                if cell.clicked:
                    count += 1
        return count >= self.size_y * self.size_x - self.num_mines

    def click(self, y: int, x: int):
        """Clicks on a cell"""
        if self.size_x < x or self.size_y < y:
            raise commands.BadArgument("Cell out side the board.")

        cell = self[x, y]

        if not self.num_mines:
            self.setup(y, x)

        if cell.flagged:
            raise commands.BadArgument("You cannot click on a flagged cell.")

        cell.clicked = True

    def flag(self, y: int, x: int):
        """Flags a cell"""
        if self.size_x < x or self.size_y < y:
            raise commands.BadArgument("Cell out side the board.")

        cell = self[x, y]

        if cell.clicked:
            raise commands.BadArgument("You cannot flag a revealed cell.")

        cell.flagged = not cell.flagged

    def clean(self):
        """Cleans up the board state"""
        for y, row in enumerate(self):
            for x, cell in enumerate(row):
                if cell.clicked and not cell.number:
                    for i in range(y - 1, y + 2):
                        for j in range(x - 1, x + 2):
                            if 0 <= i < self.size_y and 0 <= j < self.size_x and not self[j, i].clicked:
                                self[j, i].flagged = False
                                self[j, i].clicked = True
                                self.clean()


class Button(discord.ui.Button["GameUI"]):
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        super().__init__(style=discord.ButtonStyle.blurple, label="\u200b", group=y)

    @property
    def cell(self):
        return self.view.board[self.x, self.y]

    def reveal(self):
        self.disabled = True
        self.style = discord.ButtonStyle.secondary
        self.label = str(self.cell)

        if self.cell.mine:
            self.style = discord.ButtonStyle.danger
        elif self.cell.flagged:
            self.style = discord.ButtonStyle.success
        elif self.cell.clicked:
            self.label = str(self.cell.number or "\u200b")

    def click(self):
        self.view.board.click(self.y, self.x)
        self.view.board.clean()

        for child in self.view.children:
            if child.cell.clicked:  # type: ignore
                child.reveal()  # type: ignore

    async def callback(self, interaction: discord.Interaction):
        self.click()

        content = "Minesweeper!"

        if self.view.board.lost or self.view.board.solved:
            if self.view.board.lost:
                content = "💥"
            elif self.view.board.solved:
                content = "<:_:739613733474795520>"

            for child in self.view.children:
                child.disabled = True  # type: ignore

        await interaction.response.edit_message(content=content, view=self.view)


class GameUI(discord.ui.View):
    def __init__(self, player):
        self.player = player
        super().__init__(timeout=None)
        self.board = Game(5, 5)

        for r in range(5):
            for c in range(5):
                self.add_item(Button(r, c))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            await interaction.response.send_message("Sorry, you are not playing", ephemeral=True)
            return False
        return True


def is_no_game(ctx: Context):
    if ctx.channel in ctx.cog._games:
        raise commands.CheckFailure("There is already a Minesweeper game running.")
    return True


def is_game(ctx: Context):
    try:
        is_no_game(ctx)
    except commands.CheckFailure:
        return True
    raise commands.CheckFailure("No Connect Four game is running.")


class Minesweeper(Cog):
    """Simple minesweeper game"""

    def __init__(self, bot: commands.Bot):
        self._games: dict[discord.TextChannel, Game] = {}

    @commands.group(name="minesweeper", aliases=["ms"], invoke_without_command=True)
    async def minesweeper(self, ctx):
        """Minesweeper game commands"""
        pass

    @minesweeper.group(name="start")
    @commands.check(is_no_game)
    # @commands.check(is_war_channel)
    async def ms_start(self, ctx):
        """Starts a Minesweeper game"""
        if ctx.invoked_subcommand is None:
            game = GameUI(ctx.author)
            await ctx.send("Minesweeper!", view=game)  # type: ignore

    @ms_start.command(name="tiny")
    async def ms_start_tiny(self, ctx):
        """Starts a easy difficulty Minesweeper game"""
        game = self._games[ctx.channel] = Game(5, 5)
        game.last_state = await ctx.send(
            f"Minesweeper Game Started!\n>>> {game}\n\nReveal cells with `{ctx.prefix}ms click`."
        )

    @ms_start.command(name="easy")
    async def ms_start_easy(self, ctx):
        """Starts a easy difficulty Minesweeper game"""
        game = self._games[ctx.channel] = Game(10, 7)
        game.last_state = await ctx.send(
            f"Minesweeper Game Started!\n>>> {game}\n\nReveal cells with `{ctx.prefix}ms click`."
        )

    @ms_start.command(name="medium")
    async def ms_start_medium(self, ctx):
        """Starts a medium difficulty Minesweeper game"""
        game = self._games[ctx.channel] = Game(17, 8)
        game.last_state = await ctx.send(
            f"Minesweeper Game Started!\n>>> {game}\n\nReveal cells with `{ctx.prefix}ms click`."
        )

    # @ms_start.command(name='hard')
    # async def ms_start_hard(self, ctx):
    #     """Starts a hard difficulty Minesweeper game"""
    #     game = self._games[ctx.channel] = Game(26, 10)
    #     game.last_state = await ctx.send(f'Minesweeper Game Started!\n>>> {game}\n\nReveal cells with `{ctx.prefix}ms click`.')

    @minesweeper.command(name="click")
    @commands.check(is_game)
    async def ms_click(self, ctx: Context, cells: commands.Greedy[boardgames.Cell]):
        """Clicks a cell on the board.

        cells are referenced by column then row for example `A2`"""

        game = self._games[ctx.channel]

        for cell in cells:
            game.click(*cell)

        game.clean()

        message = ""
        if game.lost:
            message += "\nToo bad, you lose."
        elif game.solved:
            message += "\nCongratulations, you win! <:_:739613733474795520>"

        if game.last_state is not None:
            try:
                await game.last_state.delete()
            except Exception:
                pass
        game.last_state = await ctx.send(f">>> {game}" + message)

        # If game over delete the game.
        if game.lost or game.solved:
            del self._games[ctx.channel]

    @minesweeper.command(name="flag", aliases=["guess"])
    @commands.check(is_game)
    async def ms_flag(self, ctx: Context, cells: commands.Greedy[boardgames.Cell]):
        """Flags a cell on the board.

        cells are referenced by column then row for example `A2`"""

        game = self._games[ctx.channel]

        for cell in cells:
            game.flag(*cell)

        if game.last_state is not None:
            try:
                await game.last_state.delete()
            except Exception:
                pass
        game.last_state = await ctx.send(f">>> {game}")


def setup(bot: commands.Bot):
    bot.add_cog(Minesweeper(bot))
