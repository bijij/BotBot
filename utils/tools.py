import datetime

import discord
from discord.ext import commands

from asyncio import ensure_future
from numbers import Number
from typing import Optional, Union, Iterable, cast


__all__ = (
    'add_reactions',
    'format_dt',
    'ordinal',
    'regional_indicator',
    'keycap_digit',
    'plural',
    'RawMessage'
)


def format_dt(dt: datetime.datetime) -> str:
    """Formats datetime strings.

    Args:
        dt: (datetime.datetime): The datetime object to format.
    """
    return dt.strftime('%F @ %T UTC')


def ordinal(n):
    """Determines The ordinal for a given integer."""
    return f'{n}{"tsnrhtdd"[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10 :: 4]}'


class plural:

    def __init__(self, value: Number):
        self.value = value

    def __format__(self, format_spec: str):
        singular, _, plural = format_spec.partition('|')
        plural = plural or f'{singular}s'
        return f'{self.value} {plural if abs(self.value) != 1 else singular}'  # type: ignore


def regional_indicator(c: str) -> str:
    """Returns a regional indicator emoji given a character."""
    return chr(0x1f1e6 - ord('A') + ord(c.upper()))


def keycap_digit(c: Union[int, str]) -> str:
    """Returns a keycap digit emoji given a character."""
    return (str(c).encode('utf-8') + b'\xe2\x83\xa3').decode('utf-8')


async def add_reactions(message: discord.Message, reactions: Iterable[Union[str, discord.Emoji]]):
    """Adds reactions to a message

    Args:
        message (discord.Message): The message to react to.
        reactions (): A set of reactions to add.
    """
    async def react():
        for reaction in reactions:
            await message.add_reaction(reaction)

    ensure_future(react())


async def confirm(bot: commands.Bot, message: Union[str, discord.Message], user: discord.User, *, channel: Optional[discord.TextChannel] = None, timeout=60, delete_after=True):
    if isinstance(message, str):
        message = await channel.send(message)
        message = cast(discord.Message, message)

    confirm = False
    reactions = ['\N{thumbs up sign}', '\N{thumbs down sign}']

    def check(payload):
        message = cast(discord.Message, message)
        return payload.message_id == message.id and payload.user_id == user.id and str(payload.emoji) in reactions

    await add_reactions(message, reactions)

    try:
        payload = await bot.wait_for('raw_reaction_add', check=check, timeout=timeout)
        if str(payload.emoji) == '\N{thumbs up sign}':
            confirm = True
    finally:
        if delete_after:
            await message.delete()

        return confirm


class RawMessage(discord.Message):
    """Stateless Discord Message object.
    Args:
        client (discord.Client): The client which will alter the message.
        channel (discord.TextChannel): The channel the message is in.
        message_id (int): The message's ID.
    """

    def __init__(self, client, channel, message_id):
        self._state = client._connection
        self.id = message_id
        self.channel = channel

    def __repr__(self):
        return f'<RawMessage id={self.id} channel={self.channel}>'
