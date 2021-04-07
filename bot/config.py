import os

from typing import Any, Generic, TypeVar

import discord
from discord.client import Client
import yaml

from utils.tools import RawMessage


def load():
    with open('config.yml', encoding='UTF-8') as f:
        return yaml.load(f, Loader=yaml.FullLoader)


class HiddenRepr(str):
    def __repr__(self):
        return '<str with hidden value>'


class Object(discord.Object):
    def __init__(self, id, func):
        self._func = func
        super().__init__(id)

    def __getattribute__(self, name):
        if name in ['_func', 'id', 'created_at']:
            return object.__getattribute__(self, name)

        return getattr(self._func(), name, None)

    def __repr__(self):
        return getattr(self._func(), '__repr__', super().__repr__)()


def _env_var_constructor(loader: yaml.Loader, node: yaml.Node):
    '''Implements a custom YAML tag for loading optional environment variables.
    If the environment variable is set it returns its value.
    Otherwise returns `None`.

    Example usage:
        key: !ENV 'KEY'
    '''
    if node.id != 'scalar':  # type: ignore
        raise TypeError('Expected a string')

    value = loader.construct_scalar(node)  # type: ignore
    key = str(value)

    return HiddenRepr(os.getenv(key))


def _generate_constructor(func):

    def constructor(loader: yaml.Loader, node: yaml.Node):
        ids = [int(x) for x in loader.construct_scalar(node).split()]  # type: ignore
        return Object(ids[-1], lambda: func(*ids))

    return constructor


BotT = TypeVar('BotT', bound=Client)

class Config(yaml.YAMLObject, Generic[BotT]):
    _bot: BotT = None  # type: ignore
    yaml_tag = u'!Config'

    def __init__(self, **kwargs):
        for name, value in kwargs:
            setattr(self, name, value)

    def __getattribute__(self, name: str) -> Any:
        return super().__getattribute__(name)

    def __reload__(self):
        self.__dict__ = load().__dict__
        Config._bot.__version__ = self.VERSION  # type: ignore

    def __repr__(self):
        return f'<Config {" ".join(f"{key}={repr(value)}" for key, value in self.__dict__.items())}>'


DISCORD_CONSTRUCTORS = [

    # Discord constructors
    ('Emoji', lambda e: Config._bot.get_emoji(e)),
    ('Guild', lambda g: Config._bot.get_guild(g)),
    ('User', lambda u: Config._bot.get_user(u)),

    # Discord Guild dependant constructors
    ('Channel', lambda g, c: Config._bot.get_guild(g).get_channel(c)),
    ('Member', lambda g, m: Config._bot.get_guild(g).get_member(m)),
    ('Role', lambda g, r: Config._bot.get_guild(g).get_role(r)),
    ('Message', lambda g, c, m: RawMessage(Config._bot, Config._bot.get_guild(g).get_channel(c), m))
]


# Add constructors
yaml.FullLoader.add_constructor('!Config', Config.from_yaml)
yaml.FullLoader.add_constructor('!ENV', _env_var_constructor)

# Add discord specific constructors
for key, func in DISCORD_CONSTRUCTORS:
    yaml.FullLoader.add_constructor(
        f'!{key}', _generate_constructor(func))

# Load the config
CONFIG: Config = load()
