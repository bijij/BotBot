from functools import partial
from typing import Awaitable, Optional, Tuple

import markovify
from markovify.text import ParamError

import discord
from discord.ext import commands

from bot import BotBase, Context
from cogs.logging.logging import Message_Log, Opt_In_Status
from utils.collections import LRUDict


def make_sentence(model: markovify.Text, *, seed: str = None) -> Optional[str]:
    tries = round(54.375 * model.state_size ** 4 - 602.92 * model.state_size ** 3 + 2460.6 * model.state_size ** 2 - 3932.1 * model.state_size + 2025)

    if seed is None:
        return model.make_sentence(tries=tries)
    else:
        tries *= 2
        try:
            return model.make_sentence_with_start(beginning=seed, strict=False, tries=tries)
        except (ParamError, KeyError):
            return None


class Markov(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot
        self.model_cache = LRUDict(max_size=8)  # idk about a good size

    async def get_model(self, query: Tuple[int, ...], *coros: Awaitable[str], state_size=int) -> markovify.Text:
        # Return cached model if one exists
        if query in self.model_cache:
            return self.model_cache[query]

        # Generate the model
        data = ''
        for coro in coros:
            data += await coro
        if not data:
            raise commands.BadArgument('There was not enough message log data, please try again later.')

        def generate_model():
            model = markovify.NewlineText(input_text=data, state_size=state_size)
            return model.compile(inplace=True)

        self.model_cache[query] = m = await self.bot.loop.run_in_executor(None, generate_model)
        return m

    async def send_markov(self, ctx: Context, model: markovify.Text, seed: str = None):
        markov_call = partial(make_sentence, model, seed=seed)
        markov = await self.bot.loop.run_in_executor(None, markov_call)
        if not markov:
            raise commands.BadArgument('Markov could not be generated')

        allowed_mentions = discord.AllowedMentions(users=True)
        await ctx.send(markov, allowed_mentions=allowed_mentions)

    @commands.command(name='user_markov', aliases=['um'])
    async def user_markov(self, ctx: Context, *, user: Optional[discord.User] = None):
        """Generate a markov chain based off a users messages.

        `user`: The user who's messages should be used to generate the markov chain, defaults to you.
        """
        user = user or ctx.author

        async with ctx.typing():
            async with ctx.db as conn:
                await Opt_In_Status.is_public(ctx, user, connection=conn)

                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = (is_nsfw, 2, user.id)

                coro = Message_Log.get_user_log(user, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, state_size=2)

            await self.send_markov(ctx, model)

    @commands.command(name='seeded_user_markov', aliases=['sum'])
    async def seeded_user_markov(self, ctx: Context, user: Optional[discord.User] = None, *, seed: str):
        """Generate a markov chain based off a users messages which starts with a given seed.

        `user`: The user who's messages should be used to generate the markov chain, defaults to you.
        `seed`: The string to attempt to seed the markov chain with.
        """
        user = user or ctx.author

        async with ctx.typing():
            async with ctx.db as conn:
                await Opt_In_Status.is_public(ctx, user, connection=conn)

                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = (is_nsfw, 2, user.id)

                coro = Message_Log.get_user_log(user, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, state_size=2)

            await self.send_markov(ctx, model, seed=seed)

    @commands.command(name='dual_user_markov', aliases=['dum'])
    async def dual_user_markov(self, ctx: Context, *, user: discord.User):
        """Generate a markov chain based off you and another users messages.

        `user`: The user who's messages should be used to generate the markov chain.
        """
        if user == ctx.author:
            raise commands.BadArgument('You can\'t generate a dual user markov with yourself.')

        async with ctx.typing():
            async with ctx.db as conn:
                await Opt_In_Status.is_opted_in(ctx, connection=conn)
                await Opt_In_Status.is_public(ctx, user, connection=conn)

                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = (is_nsfw, 2, ctx.author.id, user.id)

                coro_a = Message_Log.get_user_log(ctx.author, is_nsfw, connection=conn)
                coro_b = Message_Log.get_user_log(user, is_nsfw, connection=conn)
                model = await self.get_model(query, coro_a, coro_b, state_size=2)

            await self.send_markov(ctx, model)

    @commands.command(name='guild_markov', aliases=['gm'])
    @commands.guild_only()
    async def guild_markov(self, ctx: Context):
        """Generate a markov chain based off messages in the server.
        """
        async with ctx.typing():
            async with ctx.db as conn:
                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = (is_nsfw, 3, ctx.guild.id)

                coro = Message_Log.get_guild_log(ctx.guild, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, state_size=3)

            await self.send_markov(ctx, model)

    @commands.command(name='seeded_guild_markov', aliases=['sgm'])
    async def seeded_guild_markov(self, ctx: Context, *, seed: str):
        """Generate a markov chain based off messages in the server which starts with a given seed.

        `seed`: The string to attempt to seed the markov chain with.
        """
        async with ctx.typing():
            async with ctx.db as conn:
                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = (is_nsfw, 3, ctx.guild.id)

                coro = Message_Log.get_guild_log(ctx.guild, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, state_size=3)

            await self.send_markov(ctx, model, seed=seed)


def setup(bot: BotBase):
    bot.add_cog(Markov(bot))
