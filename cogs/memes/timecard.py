import math
import random
import re

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

import discord
from discord.ext import commands


IMAGES = 'res/timecard/images'
FONT = 'res/timecard/kp.ttf'


TIMECARD_X_OFFSET = 32
TIMECARD_Y_OFFSET = 24

TIMECARD_X_BOUND = 576
TIMECARD_Y_BOUND = 432

TIMECARD_SET = [
    ['timecard_0', (226, 255, 159), None],
    ['timecard_1', (235, 4, 210), (60, 255, 23)],
    ['timecard_2', (99, 250, 208), (1, 4, 0)],
    ['timecard_3', (248, 103, 1), (32, 127, 34)],
    ['timecard_4', (8, 2, 3), None],
    ['timecard_5', (30, 234, 239), None],
    ['timecard_6', (1, 180, 235), None],
    ['timecard_7', (91, 94, 2), None],
    ['timecard_8', (250, 240, 212), (37, 53, 60)],
    ['timecard_9', (9, 160, 212), (0, 11, 23)],
    ['timecard_10', (250, 236, 255), (28, 188, 234)],
    ['timecard_11', (254, 254, 254), None],
    ['timecard_12', (252, 231, 40), None],
    ['timecard_13', (254, 254, 254), None],
    ['timecard_15', (216, 34, 148), (122, 70, 13)],
]


class TimeCard(commands.Cog):
    """Spongebob Squarepants timecard."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='timecard', aliases=['tc'])
    async def timecard(self, ctx, *, text: commands.clean_content):
        """Generate's a Spongebob Squarepants timecard image.

        `text`: The text to show on the timecard.
        """
        text = re.sub(r'\n+', '\n', text)

        async with ctx.typing():

            # Setup the image
            timecard = random.choice(TIMECARD_SET)
            img = Image.open(f'{IMAGES}/{timecard[0]}.png')
            draw = ImageDraw.Draw(img)

            # Setup the font
            font_size = 100
            font = ImageFont.truetype(FONT, font_size)

            # Resize until font fits
            while draw.textsize(text, font=font) > (TIMECARD_X_BOUND, TIMECARD_Y_BOUND):
                font_size -= 1
                font = ImageFont.truetype(FONT, font_size)

            # Determine the text location
            text_size = draw.textsize(text, font=font)
            text_x = TIMECARD_X_OFFSET + (TIMECARD_X_BOUND - text_size[0]) / 2
            text_y = TIMECARD_Y_OFFSET + (TIMECARD_Y_BOUND - text_size[1]) / 2

            # If text has drop shadow
            if timecard[2] is not None:
                drop_shadow = math.floor((font_size ** 0.5) / 2) + 1

                draw.text((text_x - drop_shadow, text_y - drop_shadow),
                          text, timecard[2], font=font)

            draw.text((text_x, text_y), text, timecard[1], font=font)

            out_fp = BytesIO()
            img.save(out_fp, 'PNG')
            out_fp.seek(0)

            await ctx.send(file=discord.File(out_fp, 'timecard.png'))


def setup(bot: commands.Bot):
    bot.add_cog(TimeCard(bot))
