from .generator import generate_random
from ampharos.types import Pokemon

import asyncio

import discord
from discord.ext import commands


async def _user_is_playing(ctx: commands.Context) -> bool:
    if ctx.author not in ctx.cog.current_games:
        raise commands.CheckFailure('You are currently not playing a game.')
    return True

def parse_generation(value):
    try:
        generation = int(value)
        if not 1 <= generation <= 8:
            raise commands.BadArgument('Generation must be between 1 and 8')
    except ValueError:
        raise commands.BadArgument('Invalid generation specified.')
    return generation

class SpeedSight(commands.Cog):
    """Swellow Sight"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.current_games = {}

    @commands.group(name='swellow_sight', aliases=['ss'])
    async def ss(self, ctx):
        """Swellow Sight commands."""
        pass

    @ss.command(name='start')
    async def start(self, ctx, *, generations: str = None):
        """Starts a Swellow Sight game.

        You'll have 120 seconds to guess which pokemon it is, go for the highest score you can.

        `generations`: What generations the pokemon should be from, can be a range or singular. e.g. 1-3 or 6.
        """

        min_gen = 1
        max_gen = 8
        if generations is not None:
            generations = generations.split('-')
            if len(generations) > 2:
                raise commands.BadArgument('Invalid generation range.')

            if len(generations) == 1:
                min_gen = max_gen = parse_generation(generations[0])
            
            else:
                min_gen = parse_generation(generations[0])
                max_gen = parse_generation(generations[1])

        if min_gen > max_gen:
            raise commands.BadArgument('Invalid generation range.')

        # Create record in database
        self.current_games[ctx.author] = 0

        streak = -1

        def check(user: discord.User, correct: bool):
            return user == ctx.author

        await ctx.send(f'Swellow Sight started, you\'ll have 120 seconds to make a guess, use `{ctx.prefix}ss guess <pokemon>`.')

        while True:

            # Send the mm image
            image, guide, answer = await generate_random(self.bot.loop, difficulty=3, min_gen=min_gen, max_gen=max_gen)
            await ctx.send(file=discord.File(image, 'ss.png'))

            streak += 1

            # Wait for guess
            try:
                _, pokemon = await self.bot.wait_for('ss_next', check=check, timeout=120)
            except asyncio.TimeoutError:
                await ctx.send('You ran out of time. Try again next week.')
                pokemon = None

            # If answer was incorrect exit
            if not pokemon == answer:
                break

        message = f'Too bad: the correct answer was **{answer.name.english}**.'

        # Send game over message
        message += f'\n\nCongratulations, you achieved a  score of **{streak}**!'
        await ctx.send(message, file=discord.File(guide, 'ss.png'))
        del self.current_games[ctx.author]

    @commands.check(_user_is_playing)
    @ss.command(name='guess')
    async def guess(self, ctx, *, pokemon: Pokemon = None):
        """Makes a guess.

        `pokemon`: The pokemon to guess.
        """
        if pokemon is None:
            return await ctx.send('No Pokemon specified please try again.')
        self.bot.dispatch('ss_next', ctx.author, pokemon)

    @commands.check(_user_is_playing)
    @ss.command(name='stop', aliases=['cancel'])
    async def guess(self, ctx):
        """Stops the current game.
        """
        self.bot.dispatch('ss_next', ctx.author, None)

def setup(bot: commands.Bot):
    bot.add_cog(SpeedSight(bot))
