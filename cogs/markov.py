from functools import partial
from typing import Optional

import asyncpg
import markovify

import discord
from discord.ext import commands

from bot import BotBase, Context
from cogs.logging import is_public


async def get_message_log(user: discord.User, conn: asyncpg.Connection) -> str:
    record = await conn.fetchrow('SELECT string_agg(content, \'\n\') AS data FROM logging.message_log WHERE user_id = $1', user.id)
    return record['data']


def get_markov(data: str, *, state_size: int = 2, seed: str = None) -> Optional[str]:
    model = markovify.NewlineText(input_text=data, state_size=state_size)

    tries = round(54.375 * state_size ** 4 - 602.92 * state_size ** 3 + 2460.6 * state_size ** 2 - 3932.1 * state_size + 2025)

    if seed is None:
        return model.make_sentence(tries=tries)
    else:
        return model.make_sentence(beginning=seed, strict=False, tries=tries)


class Markov(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

    @commands.command(name='user_markov', aliases=['um'])
    async def user_markov(self, ctx: Context, user: Optional[discord.User] = None):
        """Generate a markov chain based off a users messages.

        `user`: The user who's messages should be used to generate the markov chain, defaults to you.
        """
        user = user or ctx.author

        async with ctx.db as conn:
            await is_public(ctx, user, conn)
            data = await get_message_log(user, conn)

            if not data:
                raise commands.BadArgument(f'User "{user}" currently has no message log data, please try again later.')

        async with ctx.typing():
            markov_call = partial(get_markov, data)
            markov = await self.bot.loop.run_in_executor(None, markov_call) or '> Markov could not be generated.'
            await ctx.send(markov)


def setup(bot: BotBase):
    bot.add_cog(Markov(bot))
