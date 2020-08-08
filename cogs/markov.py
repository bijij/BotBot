from functools import partial
from random import randint
from typing import Optional

import asyncpg
import markovify
from markovify.text import ParamError

import discord
from discord.ext import commands

from bot import BotBase, Context
from cogs.logging import is_opted_in, is_public


async def get_user_message_log(user: discord.User, conn: asyncpg.Connection) -> str:
    record = await conn.fetchrow('SELECT string_agg(content, \'\n\') AS data FROM logging.message_log WHERE user_id = $1', user.id)
    return record['data']


async def get_guild_message_log(guild: discord.Guild, conn: asyncpg.Connection) -> str:
    record = await conn.fetchrow('SELECT string_agg(content, \'\n\') AS data FROM logging.message_log WHERE guild_id = $1', guild.id)
    return record['data']


def get_markov(data: str, *, state_size: int = 2, seed: str = None) -> Optional[str]:
    if state_size > 5:
        raise commands.BadArgument('State size too large to generate markov chain.')

    model = markovify.NewlineText(input_text=data, state_size=state_size)

    tries = round(54.375 * state_size ** 4 - 602.92 * state_size ** 3 + 2460.6 * state_size ** 2 - 3932.1 * state_size + 2025)

    if seed is None:
        return model.make_sentence(tries=tries)
    else:
        tries *= 2
        try:
            return model.make_sentence_with_start(beginning=seed, strict=False, tries=tries)
        except ParamError:
            return None


class Markov(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot

    @commands.command(name='user_markov', aliases=['um'])
    async def user_markov(self, ctx: Context, *, user: Optional[discord.User] = None):
        """Generate a markov chain based off a users messages.

        `user`: The user who's messages should be used to generate the markov chain, defaults to you.
        """
        user = user or ctx.author

        async with ctx.db as conn:
            await is_public(ctx, user, conn)
            data = await get_user_message_log(user, conn)

            if not data:
                raise commands.BadArgument(f'User "{user}" currently has no message log data, please try again later.')

        async with ctx.typing():
            markov_call = partial(get_markov, data, state_size=randint(2, 3))
            markov = await self.bot.loop.run_in_executor(None, markov_call)
            if not markov:
                raise commands.BadArgument('Markov could not be generated')

        await ctx.send(markov)

    @commands.command(name='seeded_user_markov', aliases=['sum'])
    async def seeded_user_markov(self, ctx: Context, user: Optional[discord.User] = None, *, seed: str):
        """Generate a markov chain based off a users messages which starts with a given seed.

        `user`: The user who's messages should be used to generate the markov chain, defaults to you.
        `seed`: The string to attempt to seed the markov chain with.
        """
        user = user or ctx.author

        async with ctx.db as conn:
            await is_public(ctx, user, conn)
            data = await get_user_message_log(user, conn)

            if not data:
                raise commands.BadArgument(f'User "{user}" currently has no message log data, please try again later.')

        async with ctx.typing():
            markov_call = partial(get_markov, data, state_size=max(len(seed.split()), 2), seed=seed)
            markov = await self.bot.loop.run_in_executor(None, markov_call)
            if not markov:
                raise commands.BadArgument('Markov could not be generated')

        await ctx.send(markov)

    @commands.command(name='dual_user_markov', aliases=['dum'])
    async def dual_user_markov(self, ctx: Context, *, user: Optional[discord.User]):
        """Generate a markov chain based off you and another users messages.

        `user`: The user who's messages should be used to generate the markov chain.
        """
        if user == ctx.author:
            raise commands.BadArgument('You can\'t generate a dual user markov with yourself.')

        async with ctx.db as conn:
            await is_opted_in(ctx, conn)
            await is_public(ctx, user, conn)
            data = await get_user_message_log(ctx.author, conn) + await get_user_message_log(user, conn)

            if not data:
                raise commands.BadArgument('There was not enough message log data, please try again later.')

        async with ctx.typing():
            markov_call = partial(get_markov, data, state_size=randint(2, 3))
            markov = await self.bot.loop.run_in_executor(None, markov_call)
            if not markov:
                raise commands.BadArgument('Markov could not be generated')

        await ctx.send(markov)

    @commands.command(name='guild_markov', aliases=['gm'])
    @commands.guild_only()
    async def guild_markov(self, ctx: Context):
        """Generate a markov chain based off messages in the server.
        """
        async with ctx.db as conn:
            data = await get_guild_message_log(ctx.guild, conn)

            if not data:
                raise commands.BadArgument(f'Server "{ctx.guild.name}" currently has no message log data, please try again later.')

        async with ctx.typing():
            markov_call = partial(get_markov, data, state_size=randint(2, 4))
            markov = await self.bot.loop.run_in_executor(None, markov_call)
            if not markov:
                raise commands.BadArgument('Markov could not be generated')

        await ctx.send(markov)


def setup(bot: BotBase):
    bot.add_cog(Markov(bot))
