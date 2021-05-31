from __future__ import annotations

import io
from typing import Optional
from PIL import Image

import discord
import vflip
from discord.ext import commands
from ditto import CONFIG, BotBase, Cog, Context
from ditto.types import User

COG_CONFIG = CONFIG.EXTENSIONS[__name__]


class ModeButton(discord.ui.Button["Mode"]):
    def __init__(self, value: Optional[vflip.types.Value]):
        self.value: Optional[vflip.types.Value] = value

        if value is None:
            style = discord.ButtonStyle.danger
            disabled = True
            label = "Flip!"
        else:
            style = discord.ButtonStyle.primary
            disabled = False
            label = str(value)

        super().__init__(style=style, label=label, disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        self.view.mode = self.value

        for button in self.view.children:
            button.disabled = False

        self.disabled = True

        await interaction.response.edit_message(view=self.view)


class Mode(discord.ui.View):
    children: list[ModeButton]

    def __init__(self, game: Game):
        super().__init__(timeout=None)
        self.game = game
        self.mode: Optional[vflip.types.Value] = None

        self.add_item(ModeButton(None))
        for n in range(4):
            self.add_item(ModeButton(n))  # type: ignore


class Button(discord.ui.Button["Game"]):
    def __init__(self, row: int, col: int):
        self.row = row
        self.col = col
        super().__init__(style=discord.ButtonStyle.success, label="\u200b", row=row)

    @property
    def square(self):
        return self.view.game[self.row, self.col]

    async def callback(self, interaction: discord.Interaction):
        if self.view.mode is None:
            self.square.flip()
        else:
            self.square.note(self.view.mode)

        if self.square.flipped:
            self.disabled = True

            if self.square.value == 0:
                self.label = "💥"
                self.style = discord.ButtonStyle.danger
            else:
                self.label = str(self.square.value)
                self.style = discord.ButtonStyle.secondary

        if self.view.game.over:
            for button in self.view.children:
                button.disabled = True
                if not button.square.flipped:
                    button.square.flip()

            self.view.stop()
            content = "Game over!"
        else:
            content = None

        embed = self.view.embed.set_image(url=await self.view.render())

        await interaction.response.edit_message(content=content, embeds=[embed], view=self.view)


class Game(discord.ui.View):
    children: list[Button]

    def __init__(self, player: User, level: int):
        self.player = player
        self.game = vflip.Board(level)  # type: ignore
        self.last_messsage = None
        self.mode_switcher = Mode(self)

        super().__init__(timeout=None)

        for row in range(5):
            for col in range(5):
                self.add_item(Button(row, col))

    @property
    def mode(self) -> Optional[vflip.types.Value]:
        return self.mode_switcher.mode

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.player:
            await interaction.response.send_message("You are not playing this game.", ephemeral=True)
            return False
        return True

    async def render(self) -> str:
        if self.last_messsage is not None:
            await self.last_messsage.delete()
        fp = io.BytesIO()

        image = self.game._render()
        image.resize((image.width * 2, image.height * 2), Image.NEAREST).save(fp, format="png")
        fp.seek(0)

        self.last_messsage = await COG_CONFIG.RENDER_CHANNEL.send(file=discord.File(fp, "voltorb.png"))
        return self.last_messsage.attachments[0].url

    def stop(self) -> None:

        for button in self.mode_switcher.children:
            button.disabled = True

        self.mode_switcher.stop()
        super().stop()

    @classmethod
    async def setup(cls, ctx: Context, level: int):
        game = cls(ctx.author, level)
        embed = game.embed.set_image(url=await game.render())
        await ctx.send(embed=embed, view=game)
        await ctx.send(content="\u200b", view=game.mode_switcher)
        return game

    @property
    def embed(self) -> discord.Embed:
        return discord.Embed()


class VoltorbFlip(Cog):
    def __init__(self, bot: BotBase) -> None:
        super().__init__(bot)
        # self.games: dict[int, Game] = {}

    @commands.command(aliases=["vf"])
    async def voltorb_flip(self, ctx: Context, level: int = 1):
        if not 0 < level <= 8:
            raise commands.BadArgument("Level must be between 1 and 8.")

        # if ctx.author.id in self.games:
        #     raise commands.BadArgument("you are already playing.")

        await Game.setup(ctx, level)


def setup(bot: BotBase):
    bot.add_cog(VoltorbFlip(bot))
