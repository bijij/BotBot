import asyncio
import io
import re

from collections import defaultdict
from typing import NameTuple

import discord
from discord.ext import commands

from ditto import BotBase, Cog, Context, CONFIG
from ditto.types.converters import PosixFlags


class Tag(NameTuple):
    tag: str
    owner_id: int
    uses: int
    can_delete: bool
    is_alias: bool
    match: str


async def has_r_danny(ctx: Context) -> bool:
    await commands.guild_only().predicate(ctx)
    if ctx.guild.get_member(CONFIG.R_DANNY.id) is None:
        raise commands.BadArgument("R.Danny is not in this server.")
    return True


PAUSE_BUTTON = "\N{DOUBLE VERTICAL BAR}"
LOADING_BUTTON = "\N{ANTICLOCKWISE DOWNWARDS AND UPWARDS OPEN CIRCLE ARROWS}"

TAG_FILE_REGEX = re.compile(
    r"^\|\s*\d+\s*\|\s*(?P<tag>.*)\s*\|\s*(?P<owner_id>\d+)\s*\|\s*(?P<uses>\d+)\s*\|\s*(?P<can_delete>(?:True)|(?:False))\s*\|\s*(?P<is_alias>(?:True)|(?:False))\s*\|$",
    re.MULTILINE,
)


class TagOptions(PosixFlags):
    claim: bool = commands.flag(default=False)


class TagChecker(Cog):
    @commands.command()
    @commands.check(has_r_danny)
    @commands.is_owner()
    async def tags(self, ctx: Context, *, options: TagOptions):
        def check(message: discord.Message):
            if message.channel != ctx.channel or message.author != CONFIG.R_DANNY:
                return False
            if len(message.attachments) != 1 or message.attachments[0].filename != "tags.txt":
                return False
            return True

        try:
            await ctx.send(
                f"{PAUSE_BUTTON} Use `@{CONFIG.R_DANNY.name}#{CONFIG.R_DANNY.discriminator} tag all --text` to retrieve the tag list.",
                delete_after=15,
            )

            message: discord.Message = await ctx.bot.wait_for("message", check=check, timeout=30)
            prefix = message.content[:-14]
        except asyncio.TimeoutError:
            return

        await ctx.send(f"{LOADING_BUTTON} Processing...", delete_after=15)

        async with ctx.typing():

            contents = await message.attachments[0].read()
            contents = contents.decode("utf-8")
            sep, contents = contents.split("\n", 1)
            key, contents = contents.split("\n", 1)

            all_tags: dict[str, Tag] = {}
            tag_owners: dict[int, list[str]] = defaultdict(list)

            for match in TAG_FILE_REGEX.finditer(contents):
                tag, owner_id, uses, can_delete, is_alias = match.groups()
                tag = tag.rstrip()
                owner_id = int(owner_id)
                uses = int(uses)
                can_delete = can_delete == "True"
                is_alias = is_alias == "True"

                all_tags[tag] = Tag(tag, owner_id, uses, can_delete, is_alias, match.group())
                tag_owners[owner_id].append(tag)

            orphaned_tags: list[str] = []

            for user_id, tags in tag_owners.items():
                if ctx.guild.get_member(user_id) is None:
                    orphaned_tags.extend(tags)

            tag_file = io.BytesIO()

            if options.claim:
                for tag in sorted(orphaned_tags, key=lambda t: all_tags[t].uses, reverse=True):
                    tag_file.write((f"{prefix}tag claim {tag}\n").encode("utf-8"))
            else:
                tag_file.write((sep + "\n").encode("utf-8"))
                tag_file.write((key + "\n").encode("utf-8"))
                tag_file.write((sep + "\n").encode("utf-8"))

                for tag in sorted(orphaned_tags, key=lambda t: all_tags[t].uses, reverse=True):
                    tag_file.write((all_tags[tag].match + "\n").encode("utf-8"))

                tag_file.write((sep + "\n").encode("utf-8"))
            tag_file.seek(0)

        await ctx.send(file=discord.File(tag_file, "available_tags.txt"))


def setup(bot: BotBase):
    bot.add_cog(TagChecker(bot))
