import datetime

from functools import partial
from typing import Awaitable, Dict, List, Optional, Tuple, Union

import rusty_snake_markov as markov

import discord
from discord.ext import commands

from bot import BotBase, Context
from cogs.logging.logging import Message_Log, Opt_In_Status
from utils.collections import TimedLRUDict


DISCORD_PY_ID = 336642139381301249
MAX_TRIES = 32


def make_sentence(model: markov.Markov, order: int, *, seed: str = None, tries=MAX_TRIES) -> Optional[str]:
    if tries > 0:
        sentence = model.generate() if seed is None else model.generate_seeded(seed)
        if len(sentence.split()) >= order * 4:  # requite sentences of at least a given size (rust's markov lib likes two word output)
            return sentence
        return make_sentence(model, order, seed=seed, tries=tries - 1)
    return None


def make_code(model: markov.Markov, order: int, *, seed: str = None, tries=MAX_TRIES * 8) -> Optional[str]:
    if tries > 0:
        sentence = model.generate()
        if "```" in sentence and len(sentence.split()) >= order * 8:
            return sentence
        return make_code(model, order, tries=tries - 1)
    return None


class Markov(commands.Cog):

    def __init__(self, bot: BotBase):
        self.bot = bot
        self.model_cache: Dict[Tuple[Union[str, int], ...], markov.Markov] = TimedLRUDict(expires_after=datetime.timedelta(minutes=30), max_size=32)

    async def get_model(self, query: Tuple[Union[str, int], ...], *coros: Awaitable[List[str]], order: int = 2) -> markov.Markov:
        # Return cached model if one exists
        if query in self.model_cache:
            return self.model_cache[query]

        # Generate the model
        data: List[str] = list()
        for coro in coros:
            data.extend(await coro)
        if not data:
            raise commands.BadArgument('There was not enough message log data, please try again later.')

        def generate_model():
            model = markov.Markov(order)
            model.train(data)
            return model

        self.model_cache[query] = m = await self.bot.loop.run_in_executor(None, generate_model)
        return m

    async def send_markov(self, ctx: Context, model: markov.Markov, order: int, *, seed: str = None, callable=make_sentence):
        markov_call = partial(callable, model, order, seed=seed)
        markov = await self.bot.loop.run_in_executor(None, markov_call)

        if not markov:
            raise commands.BadArgument('Markov could not be generated')
        if getattr(ctx.guild, 'id', None) == DISCORD_PY_ID:
            allowed_mentions = discord.AllowedMentions.none()  # <3 Moogy
        else:
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
                query = ('um', is_nsfw, 2, user.id)

                coro = Message_Log.get_user_log(user, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, order=2)

            await self.send_markov(ctx, model, 2)

    @commands.command(name='low_quality_user_markov', aliases=['lqum', 'dumb'])
    async def user_markov(self, ctx: Context, *, user: Optional[discord.User] = None):
        """Generate a markov chain based off a users messages.

        `user`: The user who's messages should be used to generate the markov chain, defaults to you.
        """
        user = user or ctx.author

        async with ctx.typing():
            async with ctx.db as conn:
                await Opt_In_Status.is_public(ctx, user, connection=conn)

                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = ('lqum', is_nsfw, 1, user.id)

                coro = Message_Log.get_user_log(user, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, order=1)

            await self.send_markov(ctx, model, 2)

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
                query = ('um', is_nsfw, 2, user.id)

                coro = Message_Log.get_user_log(user, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, order=2)

            await self.send_markov(ctx, model, 2, seed=seed.lower())

    @commands.command(name='multi_user_markov', aliases=['mum'])
    async def multi_user_markov(self, ctx: Context, *users: discord.User):
        """Generate a markov chain based off a list of users messages.

        `users`: The list of users who's messages should be used to generate the markov chain.
        """
        users = set(users)  # type: ignore
        if len(users) < 2:
            raise commands.BadArgument('You need to specify at least two users.')

        is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
        coros = []

        async with ctx.typing():
            async with ctx.db as conn:
                for user in users:
                    if user == ctx.author:
                        await Opt_In_Status.is_opted_in(ctx, connection=conn)
                    else:
                        await Opt_In_Status.is_public(ctx, user, connection=conn)

                    coros.append(Message_Log.get_user_log(user, is_nsfw, connection=conn))

                query = ('mum', is_nsfw, 3) + tuple(user.id for user in users)
                model = await self.get_model(query, *coros, order=3)

            await self.send_markov(ctx, model, 3)

    @commands.command(name='dual_user_markov', aliases=['dum'])
    async def dual_user_markov(self, ctx: Context, *, user: discord.User):
        """Generate a markov chain based off you and another users messages.

        `user`: The user who's messages should be used to generate the markov chain.
        """
        if user == ctx.author:
            raise commands.BadArgument('You can\'t generate a dual user markov with yourself.')

        await ctx.invoke(self.multi_user_markov, ctx.author, user)

    @commands.command(name='guild_markov', aliases=['gm'])
    @commands.guild_only()
    async def guild_markov(self, ctx: Context):
        """Generate a markov chain based off messages in the server.
        """
        async with ctx.typing():
            async with ctx.db as conn:
                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = ('gm', is_nsfw, 3, ctx.guild.id)

                coro = Message_Log.get_guild_log(ctx.guild, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, order=3)

            await self.send_markov(ctx, model, 3)

    @commands.command(name='code_guild_markov', aliases=['cgm'])
    @commands.guild_only()
    async def code_guild_markov(self, ctx: Context):
        """Generate a markov chain code block.
        """
        async with ctx.typing():
            async with ctx.db as conn:
                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = ('cgm', is_nsfw, 2, ctx.guild.id)

                coro = Message_Log.get_guild_log(ctx.guild, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, order=2)

            await self.send_markov(ctx, model, 2, callable=make_code)

    @commands.command(name='code_user_markov', aliases=['cum'])
    async def code_user_markov(self, ctx: Context, user: Optional[discord.User] = None):
        """Generate a markov chain code block.
        """
        user = user or ctx.author

        async with ctx.typing():
            async with ctx.db as conn:
                await Opt_In_Status.is_public(ctx, user, connection=conn)

                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = ('cum', is_nsfw, 2, user.id)

                coro = Message_Log.get_user_log(user, is_nsfw, connection=conn)
                model = await self.get_model(query, coro, order=2)

            await self.send_markov(ctx, model, 2, callable=make_code)

    @commands.command(name='seeded_guild_markov', aliases=['sgm'])
    async def seeded_guild_markov(self, ctx: Context, *, seed: str):
        """Generate a markov chain based off messages in the server which starts with a given seed.

        `seed`: The string to attempt to seed the markov chain with.
        """
        async with ctx.typing():
            async with ctx.db as conn:
                is_nsfw = ctx.channel.is_nsfw() if ctx.guild is not None else False
                query = ('gm', is_nsfw, 3, ctx.guild.id)

                coro = Message_Log.get_guild_log(ctx.guild, is_nsfw, False, connection=conn)
                model = await self.get_model(query, coro, order=3)

            await self.send_markov(ctx, model, 3, seed=seed.lower())


def setup(bot: BotBase):
    bot.add_cog(Markov(bot))
