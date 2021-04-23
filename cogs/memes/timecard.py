import random

from collections import namedtuple
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

import discord
from discord.ext import commands


Timecard = namedtuple("Timecard", "filename colour shadow_colour")


IMAGES = "res/timecard/images"
FONT = "res/timecard/kp.ttf"

TIMECARD_X_OFFSET = 32
TIMECARD_Y_OFFSET = 24

TIMECARD_X_BOUND = 576
TIMECARD_Y_BOUND = 432

TIMECARD_SET = [
    Timecard("0", (226, 255, 159), None),
    Timecard("1", (235, 4, 210), (60, 255, 23)),
    Timecard("2", (99, 250, 208), (1, 4, 0)),
    Timecard("3", (248, 103, 1), (32, 127, 34)),
    Timecard("4", (8, 2, 3), None),
    Timecard("5", (30, 234, 239), None),
    Timecard("6", (1, 180, 235), None),
    Timecard("7", (91, 94, 2), None),
    Timecard("8", (250, 240, 212), (37, 53, 60)),
    Timecard("9", (9, 160, 212), (0, 11, 23)),
    Timecard("10", (250, 236, 255), (28, 188, 234)),
    Timecard("11", (254, 254, 254), None),
    Timecard("12", (252, 231, 40), None),
    Timecard("13", (254, 254, 254), None),
    Timecard("14", (70, 109, 40), None),
    Timecard("15", (216, 34, 148), (122, 70, 13)),
]


class TimeCard(commands.Cog):
    """Spongebob Squarepants timecard."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="timecard", aliases=["tc"])
    async def timecard(self, ctx, *, text: commands.clean_content(fix_channel_mentions=True)):  # type: ignore
        """Generate's a Spongebob Squarepants timecard image.

        `text`: The text to show on the timecard.
        """
        async with ctx.typing():
            timecard: Timecard = random.choice(TIMECARD_SET)

            # Load image
            image = Image.open(f"{IMAGES}/timecard_{timecard.filename}.png")
            draw = ImageDraw.Draw(image)

            # Setup font
            font_size = 100
            font = ImageFont.truetype(FONT, font_size)

            # Calculate font-size
            while (text_size := draw.textsize(text, font=font)) > (
                TIMECARD_X_BOUND,
                TIMECARD_Y_BOUND,
            ):
                font_size -= 1
                font = ImageFont.truetype(FONT, font_size)

            # Calculate Starting Y position
            y_pos = TIMECARD_Y_OFFSET + (TIMECARD_Y_BOUND - text_size[1]) // 2

            # Draw text
            for line in (lines := text.split("\n")) :

                line_width, _ = draw.textsize(line, font=font)
                x_pos = TIMECARD_X_OFFSET + (TIMECARD_X_BOUND - line_width) // 2

                if timecard.shadow_colour is not None:
                    shadow_offset = int(font_size ** 0.5 / 2) + 1
                    draw.text(
                        (x_pos - shadow_offset, y_pos - shadow_offset),
                        line,
                        timecard.shadow_colour,
                        font=font,
                    )

                draw.text((x_pos, y_pos), line, timecard.colour, font=font)

                y_pos += text_size[1] // len(lines)

            out_fp = BytesIO()
            image.save(out_fp, "PNG")
            out_fp.seek(0)

            await ctx.send(file=discord.File(out_fp, "timecard.png"))


def setup(bot: commands.Bot):
    bot.add_cog(TimeCard(bot))
