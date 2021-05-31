from __future__ import annotations

import io

import discord
import vflip
from discord.ext import commands
from ditto import CONFIG, BotBase, Cog, Context
from ditto.types import User

COG_CONFIG = CONFIG.EXTENSIONS[__name__]


class Button(discord.ui.Button["Game"]):
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        super().__init__(style=discord.ButtonStyle.success, row=y)

    async def callback(self, interaction: discord.Interaction):
        self.view.game[self.x, self.y].flip()
        self.disabled = True

        if self.view.game.over:
            for button in self.view.children:
                button.disabled = True

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

        super().__init__(timeout=None)

        for x in range(5):
            for y in range(5):
                self.add_item(Button(x, y))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.player:
            await interaction.response.send_message("You are not playing this game.", ephemeral=True)
            return False
        return True

    async def render(self) -> str:
        if self.last_messsage is not None:
            await self.last_messsage.delete()
        fp = io.BytesIO()

        self.game._render().save(fp, format="png")
        fp.seek(0)

        self.last_messsage = await COG_CONFIG.RENDER_CHANNEL.send(file=discord.File(fp, "voltorb.png"))
        return self.last_messsage.attachments[0].url

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

        game = Game(ctx.author, level)
        embed = game.embed.set_image(url=await game.render())
        await ctx.send(embed=embed, view=game)


def setup(bot: BotBase):
    bot.add_cog(VoltorbFlip(bot))
