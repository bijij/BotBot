import io
from typing import cast

from PIL import Image, ImageDraw, ImageFont

from ditto import CONFIG as BOT_CONFIG

import discord
from discord.ext import commands
from discord.utils import MISSING
from ditto.config import CONFIG


CONFIG = BOT_CONFIG.EXTENSIONS[__name__]

IMAGE = "res/imagine.png"
TITLE_FONT = CONFIG.TITLE_FONT
BYLINE_FONT = CONFIG.BYLINE_FONT

IMAGE_WIDTH = 2048
IMAGE_HEIGHT = 1024

TITLE_OFFSET = (128, 192)
TITLE_BOUND = (IMAGE_WIDTH - (TITLE_OFFSET[0] * 2), IMAGE_HEIGHT - 224 - TITLE_OFFSET[1])

BYLINE_OFFSET = (TITLE_OFFSET[0] * 2, TITLE_OFFSET[1] + TITLE_BOUND[1])
BYLINE_BOUND = (IMAGE_WIDTH - (BYLINE_OFFSET[0] * 2), 192)

WHITE = (255, 255, 255)


def draw_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_name: str,
    colour: tuple[int, int, int],
    bounds: tuple[int, int],
    offsets: tuple[int, int],
    max_font_size: int,
    max_spacing: int = MISSING,
) -> None:
    font_size = max_font_size
    spacing = max_spacing or 0

    # Calculate font size
    while True:
        font = ImageFont.truetype(font_name, font_size)
        text_size = cast(tuple[int, int], draw.textsize(text, font=font, spacing=spacing))
        if text_size[0] < bounds[0] and text_size[1] < bounds[1]:
            break

        font_size -= 1
        if max_spacing is not MISSING:
            sign = (-1, 1)[max_spacing < 0]
            spacing = int(sign * font_size * (abs(max_spacing) / max_font_size))

    # Calculate Starting Y position
    y_pos = offsets[1] + (bounds[1] - text_size[1]) // 2

    # Draw text
    lines = text.split("\n")
    for line in lines:
        line_width, _ = draw.textsize(line, font=font)  # type: ignore
        x_pos = offsets[0] + (bounds[0] - line_width) // 2
        draw.text((x_pos, y_pos), line, colour, font=font)
        y_pos += text_size[1] // len(lines)


class Imagine(commands.Cog):
    @commands.command(name="imagine")
    async def timecard(self, ctx, *, text: commands.clean_content(fix_channel_mentions=True) = "a place\nfor friends and communities"):  # type: ignore
        """Imagine."""
        async with ctx.typing():
            # Load image
            image = Image.open(IMAGE)
            draw = cast(ImageDraw.ImageDraw, ImageDraw.Draw(image))

            title, _, byline = str(text).upper().partition("\n")

            if "\n" in byline:
                raise commands.BadArgument("Too many lines in input.")

            title = f"IMAGINE\n{title}"

            draw_text(draw, title, TITLE_FONT, WHITE, TITLE_BOUND, TITLE_OFFSET, 300, -96)
            draw_text(draw, byline, BYLINE_FONT, WHITE, BYLINE_BOUND, BYLINE_OFFSET, 100)

            out_fp = io.BytesIO()
            image.save(out_fp, "PNG")
            out_fp.seek(0)

            await ctx.send(file=discord.File(out_fp, "imagine.png"))


def setup(bot: commands.Bot):
    bot.add_cog(Imagine(bot))
