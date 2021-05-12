import io

from PIL import Image, ImageDraw, ImageFont

from ditto import CONFIG as BOT_CONFIG

import discord
from discord.ext import commands
from ditto.config import CONFIG


CONFIG = BOT_CONFIG.EXTENSIONS[__name__]

IMAGE = "res/imagine.png"
TITLE_FONT = CONFIG.TITLE_FONT
BYLINE_FONT = CONFIG.BYLINE_FONT

IMAGE_WIDTH = 2048
IMAGE_HEIGHT = 1024

TEXT_X_OFFSET = 128
TEXT_Y_OFFSET = 192

TEXT_X_BOUND = IMAGE_WIDTH - (TEXT_X_OFFSET * 2)
TEXT_Y_BOUND = IMAGE_HEIGHT - 224 - TEXT_Y_OFFSET

BYLINE_Y_OFFSET = TEXT_Y_OFFSET + TEXT_Y_BOUND

BYLINE_X_BOUND = IMAGE_WIDTH - (TEXT_X_OFFSET * 4)
BYLINE_Y_BOUND = 192

WHITE = (255, 255, 255)


class Imagine(commands.Cog):
    @commands.command(name="imagine")
    async def timecard(self, ctx, *, text: commands.clean_content(fix_channel_mentions=True) = "a place\nfor friends and communities"):  # type: ignore
        """Imagine."""
        async with ctx.typing():
            # Load image
            image = Image.open(IMAGE)
            draw = ImageDraw.Draw(image)

            title, _, byline = str(text).upper().partition("\n")

            if "\n" in byline:
                raise commands.BadArgument("Too many lines in input.")

            title = f"IMAGINE\n{title}"

            # Draw title

            # Setup font
            font_size = 300
            spacing = -96
            font = ImageFont.truetype(TITLE_FONT, font_size)

            # Calculate font-size
            while (text_size := draw.textsize(title, font=font, spacing=spacing)) > (
                TEXT_X_BOUND,
                TEXT_Y_BOUND,
            ):
                font_size -= 1
                spacing = int(-font_size * (96 / 300))
                font = ImageFont.truetype(TITLE_FONT, font_size)

            # Calculate Starting Y position
            y_pos = TEXT_Y_OFFSET + (TEXT_Y_BOUND - text_size[1]) // 2

            # Draw text
            lines = title.split("\n")
            for line in lines:
                line_width, _ = draw.textsize(line, font=font)
                x_pos = TEXT_X_OFFSET + (TEXT_X_BOUND - line_width) // 2
                draw.text((x_pos, y_pos), line, WHITE, font=font)
                y_pos += text_size[1] // len(lines)

            # Draw byline

            font_size = 100
            font = ImageFont.truetype(BYLINE_FONT, font_size)

            # Calculate font-size
            while (text_size := draw.textsize(byline, font=font)) > (
                BYLINE_X_BOUND,
                BYLINE_Y_BOUND,
            ):
                font_size -= 1
                font = ImageFont.truetype(BYLINE_FONT, font_size)

            # Calculate Starting Y position
            y_pos = BYLINE_Y_OFFSET + (BYLINE_Y_BOUND - text_size[1]) // 2

            # Draw text
            lines = byline.split("\n")
            for line in lines:
                line_width, _ = draw.textsize(line, font=font)
                x_pos = TEXT_X_OFFSET + (TEXT_X_BOUND - line_width) // 2
                draw.text((x_pos, y_pos), line, WHITE, font=font)
                y_pos += text_size[1] // len(lines)

            out_fp = io.BytesIO()
            image.save(out_fp, "PNG")
            out_fp.seek(0)

            await ctx.send(file=discord.File(out_fp, "imagine.png"))


def setup(bot: commands.Bot):
    bot.add_cog(Imagine(bot))
