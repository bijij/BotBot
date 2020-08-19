import discord

from asyncio import ensure_future
from numbers import Number
from typing import Union, Iterable

__all__ = (
    'add_reactions',
    'regional_indicator',
    'keycap_digit',
    'plural'
)


class plural:

    def __init__(self, value: Number):
        self.value = value

    def __format__(self, format_spec: str):
        singular, _, plural = format_spec.partition('|')
        plural = plural or f'{singular}s'
        return f'{self.value} {plural if abs(self.value) != 1 else singular}'


def regional_indicator(c: str) -> str:
    """Returns a regional indicator emoji given a character."""
    return chr(0x1f1e6 - ord('A') + ord(c.upper()))


def keycap_digit(c: Union[int, str]) -> str:
    """Returns a keycap digit emoji given a character."""
    return (str(c).encode('utf-8') + b'\xe2\x83\xa3').decode('utf-8')


async def add_reactions(message: discord.Message, reactions: Iterable[discord.Emoji]):
    """Adds reactions to a message

    Args:
        message (discord.Message): The message to react to.
        reactions (): A set of reactions to add.
    """
    async def react():
        for reaction in reactions:
            await message.add_reaction(reaction)

    ensure_future(react())