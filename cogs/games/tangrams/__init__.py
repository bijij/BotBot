import discord
from discord.ext import commands, menus

from .puzzle import Board


BLACK_SQUARE = "⬛"
WHITE_SQUARE = "⬜"
PIECES = ["🟥", "🟫", "🟧", "🟨", "🟩", "🟦", "🟪"]

TEST_BOARD = [
    "------------",
    "------------",
    "------------",
    "-----aa-----",
    "-b---aa-----",
    "-bbccccdd---",
    "--befffgdd--",
    "---e-f-g----",
    "--ee---gg---",
    "------------",
    "------------",
]


class TangramMenu(menus.Menu):
    async def send_initial_message(self, ctx, channel):
        return await channel.send(embed=discord.Embed(description=self.state))

    async def start(self, ctx):
        self.x = 0
        self.y = 0
        self.i = 0

        self.positions: list[tuple[int, int]] = [(self.x, self.y)]
        self.board = Board.from_string(TEST_BOARD)
        self.piece = self.board.pieces[0]

        return await super().start(ctx, wait=True)

    async def _update(self):
        await self.message.edit(embed=discord.Embed(description=self.state))

    @property
    def state(self) -> str:
        out = []

        for row in self.board.state:
            outr = ""
            for col in row:
                outr += WHITE_SQUARE if col else BLACK_SQUARE
            out.append(outr)

        for position, piece, emoji in zip(self.positions, self.board.pieces, PIECES):
            for y, row in enumerate(piece.state, position[1]):
                for x, col in enumerate(row, position[0]):
                    if col:
                        out[y] = out[y][:x] + emoji + out[y][x + 1 :]

        return "\n".join(out)

    @menus.button("🔼")
    async def up(self, payload):
        if self.y == 0:
            return
        self.y -= 1
        self.positions[self.i] = (self.x, self.y)
        await self._update()

    @menus.button("🔽")
    async def down(self, payload):
        if self.y + len(self.piece.state) == len(self.board.state):
            return
        self.y += 1
        self.positions[self.i] = (self.x, self.y)
        await self._update()

    @menus.button("◀️")
    async def left(self, payload):
        if self.x == 0:
            return
        self.x -= 1
        self.positions[self.i] = (self.x, self.y)
        await self._update()

    @menus.button("▶️")
    async def right(self, payload):
        if self.x + len(self.piece.state[0]) == len(self.board.state[0]):
            return
        self.x += 1
        self.positions[self.i] = (self.x, self.y)
        await self._update()

    @menus.button("⏺️")
    async def place(self, payload):
        self.i += 1

        if self.i != len(self.board.pieces):
            self.piece = self.board.pieces[self.i]
            self.x = 0
            self.y = 0
            self.positions.append((self.x, self.y))
            return await self._update()

        if self.board.test_solution(self.positions):
            await self.ctx.send("Congratulations!")
            # // TODO: GG

        else:
            await self.ctx.send("Better luck next time!")

        self.stop()

    @menus.button("⏏️")
    async def reset(self, payload):
        self.i = 0
        self.x = 0
        self.y = 0
        self.positions = [(self.x, self.y)]
        self.piece = self.board.pieces[0]

        await self._update()

    @menus.button("⏹️")
    async def quit(self, payload):
        self.stop()


class Tangrams(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.max_concurrency(1, per=commands.BucketType.channel)
    @commands.command(name="tg", hidden=True)
    async def tg_test(self, ctx):
        m = TangramMenu(clear_reactions_after=True)
        await m.start(ctx)


def setup(bot: commands.Bot):
    bot.add_cog(Tangrams(bot))
