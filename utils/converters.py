from bot import Context
from discord.ext.commands import Converter
from .objects import Code


class CodeConverter(Converter):
    async def convert(self, ctx: Context, argument: str):
        if argument.startswith('```') and argument.endswith('```'):
            return Code('\n'.join(argument.split('\n')[1:-1]))
        return Code(argument)


__converters__ = {
    Code: CodeConverter,
}
