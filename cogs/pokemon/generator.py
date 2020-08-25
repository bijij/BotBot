import functools

import ampharos

from io import BytesIO
from math import ceil
from random import randint
from PIL import Image, ImageDraw


ASSETS_DIR = 'bot/cogs/events/mystery_monday/assets'
MAX_TRIES = 1000


def has_transparency(im: Image) -> bool:
    """Checks if an image has any transparency"""

    # Get list of pixels
    pixels = list(im.getdata())

    for pixel in pixels:
        # check if alpha channel is not 100% opaque
        if pixel[3] < 255:
            return True

    # Otherwise return false
    return False


def has_contrast(im: Image, difficulty: float) -> bool:
    """checks the image has contrasting colours"""

    # Get list of pixels
    pixels = im.getdata()
    colours = set()

    # average out the colours
    for pixel in pixels:
        result = tuple(round(x / 16) for x in pixel[0:3])
        colours.add((result))

    # Check there is a relatively high amount of varying colours
    return len(colours) >= 30 * difficulty


def render_image(im: Image, output_scale: int):
    """Renders the mystery moonday image from a crop"""

    # Resize and get list of pixels
    image_data = list(im.getdata())

    # Load the filter image
    filter_overlay = list(Image.open(
        f'{ASSETS_DIR}/filter_{int(150 * output_scale)}.png').getdata())

    # Apply the filter to the image
    for index, pixel in enumerate(filter_overlay):
        x, y = (pixel % int(15 * output_scale) for pixel in pixel[0:2])
        filter_overlay[index] = (image_data[y * int(15 * output_scale) + x])

    # Save the image
    im = Image.new('RGBA', (int(150 * output_scale), int(150 * output_scale)))
    im.putdata(filter_overlay)

    f = BytesIO()
    im.save(f, 'PNG')
    f.seek(0)
    return f


def render_guide(im: Image, crop: Image, left: int, top: int):
    """Renders a bounding box where the crop is from"""
    draw = ImageDraw.Draw(im)
    crop_size = crop.size[0]

    # Draw a bonding box at i thickness
    for i in range(3):
        draw.rectangle([(left - 1 - i, top - 1 - i), (left + crop_size + i, top + crop_size + i)], outline=(255, 0, 0))

    # Save the image
    f = BytesIO()
    im.save(f, 'PNG')
    f.seek(0)
    return f


def generate(pokemon: str, *, difficulty=1):
    """Generates a mystery monday image and accompanying guide"""

    # Load Image from file
    im = Image.open(f'{ASSETS_DIR}/pokemon/{pokemon}.png')

    # do not change this without rendering a new transformation image
    crop_size = ceil(15 * difficulty)

    i = 0
    while i < MAX_TRIES:
        # Generate a crop
        left, top = randint(
            0, im.size[0] - crop_size), randint(0, im.size[1] - crop_size)
        crop = im.crop((left, top, left + crop_size, top + crop_size))

        # check for transparency and contrast
        if not has_transparency(crop) and has_contrast(crop, difficulty):
            break

        i += 1

    if i == MAX_TRIES:
        raise OSError(f'Could not generate MM for pokemon {pokemon}')

    # Render the image and guide
    return (render_image(crop, difficulty), render_guide(im, crop, left, top))


async def generate_random(loop, *, difficulty=1):
    """Generates a random mystery monday image"""
    while True:
        try:
            pkmn = await ampharos.random_pokemon()

            # Skip alternate forms for now.
            # Will remove this eventually.
            if ' ' in pkmn._term:
                continue

            func = functools.partial(
                generate, pokemon=pkmn.pokedex_number, difficulty=difficulty)
            image, guide = await loop.run_in_executor(None, func)
            return image, guide, pkmn

        except OSError:
            pass
