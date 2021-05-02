import asyncpg
import discord

from discord.ext import commands
from donphan import Column, Enum, SQLType, Table

from ditto import Context
from donphan.types import EnumType


class MessageLog(Table, schema="logging"):  # type: ignore
    channel_id: Column[SQLType.BigInt] = Column(primary_key=True)
    message_id: Column[SQLType.BigInt] = Column(primary_key=True, unique=True)
    guild_id: Column[SQLType.BigInt] = Column(index=True)
    user_id: Column[SQLType.BigInt] = Column(index=True)
    content: Column[str]
    nsfw: Column[bool] = Column(default=False)
    deleted: Column[bool] = Column(default=False)

    @classmethod
    async def get_user_log(
        cls,
        connection: asyncpg.Connection,
        user: discord.User,
        nsfw: bool = False,
        flatten_case: bool = False,
    ) -> list[str]:
        query = f"""
            SELECT * FROM (SELECT message_id, content, user_id, deleted, nsfw from {MessageLog._name}
            UNION SELECT b.message_id, b.content, a.user_id, a.deleted, a.nsfw from {MessageAttachments._name}  AS b
            INNER JOIN {MessageLog._name} AS a ON (a.message_id = b.message_id)
            ) _ WHERE deleted = false AND user_id = $1 AND nsfw <= $2 AND content LIKE '% %';
        """
        data = await connection.fetch(query, user.id, nsfw)
        return [record["content"].lower() if flatten_case else record["content"] for record in data]

    @classmethod
    async def get_guild_log(
        cls,
        connection: asyncpg.Connection,
        guild: discord.Guild,
        nsfw: bool = False,
        flatten_case: bool = False,
    ) -> list[str]:
        query = f"""
            SELECT * FROM (SELECT message_id, content, guild_id, deleted, nsfw from {MessageLog._name}
            UNION SELECT b.message_id, b.content, a.guild_id, a.deleted, a.nsfw from {MessageAttachments._name} AS b
            INNER JOIN {MessageLog._name} AS a ON (a.message_id = b.message_id)
            ) _ WHERE deleted = false AND guild_id = $1 AND nsfw <= $2 AND content LIKE '% %';
        """
        data = await connection.fetch(query, guild.id, nsfw)
        return [record["content"].lower() if flatten_case else record["content"] for record in data]


class MessageAttachments(Table, schema="logging"):  # type: ignore
    message_id: Column[SQLType.BigInt] = Column(primary_key=True, references=MessageLog.message_id)
    attachment_id: Column[SQLType.BigInt]
    content: Column[str]


class MessageEditHistory(Table, schema="logging"):  # type: ignore
    message_id: Column[SQLType.BigInt] = Column(primary_key=True, references=MessageLog.message_id)
    created_at: Column[SQLType.Timestamp] = Column(primary_key=True)
    content: Column[str]


class Status(Enum):
    online = 1
    offline = 2
    idle = 3
    dnd = 4
    streaming = 5


class _Status(EnumType[Status], name="status", schema="logging"):  # Hack from porting donphan v3 > v4
    ...

class StatusLog(Table, schema="logging"):  # type: ignore
    user_id: Column[SQLType.BigInt] = Column(primary_key=True, index=True)
    timestamp: Column[SQLType.Timestamp] = Column(primary_key=True)
    status: Column[_Status]


class OptInStatus(Table, schema="logging"):  # type: ignore
    user_id: Column[SQLType.BigInt] = Column(primary_key=True, index=True)
    public: Column[bool] = Column(default=False)
    nsfw: Column[bool] = Column(default=False)

    @classmethod
    async def is_opted_in(cls, connection: asyncpg.Connection, ctx: Context):
        opt_in_status = await cls.fetch_row(connection, user_id=ctx.author.id)
        if opt_in_status is None:
            raise commands.BadArgument(
                f"You have not opted in to logging. You can do so with `{ctx.bot.prefix}logging start`"
            )

    @classmethod
    async def is_not_opted_in(cls, connection: asyncpg.Connection, ctx: Context):
        opt_in_status = await cls.fetch_row(connection, user_id=ctx.author.id)
        if opt_in_status is not None:
            raise commands.BadArgument("You have already opted into logging.")

    @classmethod
    async def is_public(cls, connection: asyncpg.Connection, ctx: Context, user: discord.User):
        opt_in_status = await cls.fetch_row(connection, user_id=user.id)
        if opt_in_status is None:
            if user == ctx.author:
                raise commands.BadArgument(
                    f"You have not opted in to logging. You can do so with `{ctx.bot.prefix}logging start`"
                )
            else:
                raise commands.BadArgument(f'User "{user}" has not opted in to logging.')

        if user != ctx.author and not opt_in_status["public"]:
            raise commands.BadArgument(f'User "{user}" has not made their logs public.')
