import asyncpg
import discord

from discord.ext import commands
from donphan import Column, enum, MaybeAcquire, SQLType, Table

from ditto import Context


class Message_Log(Table, schema="logging"):  # type: ignore
    channel_id: SQLType.BigInt = Column(primary_key=True)
    message_id: SQLType.BigInt = Column(primary_key=True, unique=True)
    guild_id: SQLType.BigInt = Column(index=True)
    user_id: SQLType.BigInt = Column(index=True)
    content: str
    nsfw: SQLType.Boolean = Column(default=False)
    deleted: SQLType.Boolean = Column(default=False)

    @classmethod
    async def get_user_log(
        cls,
        user: discord.User,
        nsfw: bool = False,
        flatten_case: bool = False,
        *,
        connection: asyncpg.Connection = None,
    ) -> list[str]:
        async with MaybeAcquire(connection) as connection:
            query = f"""
                SELECT * FROM (SELECT message_id, content, user_id, deleted, nsfw from {Message_Log._name}
                UNION SELECT b.message_id, b.content, a.user_id, a.deleted, a.nsfw from {Message_Attachments._name}  AS b
                INNER JOIN {Message_Log._name} AS a ON (a.message_id = b.message_id)
                ) _ WHERE deleted = false AND user_id = $1 AND nsfw <= $2 AND content LIKE '% %';
            """
            data = await connection.fetch(query, user.id, nsfw)
        return [record["content"].lower() if flatten_case else record["content"] for record in data]

    @classmethod
    async def get_guild_log(
        cls,
        guild: discord.Guild,
        nsfw: bool = False,
        flatten_case: bool = False,
        *,
        connection: asyncpg.Connection = None,
    ) -> list[str]:
        async with MaybeAcquire(connection) as connection:
            query = f"""
                SELECT * FROM (SELECT message_id, content, guild_id, deleted, nsfw from {Message_Log._name}
                UNION SELECT b.message_id, b.content, a.guild_id, a.deleted, a.nsfw from {Message_Attachments._name}  AS b
                INNER JOIN {Message_Log._name} AS a ON (a.message_id = b.message_id)
                ) _ WHERE deleted = false AND guild_id = $1 AND nsfw <= $2 AND content LIKE '% %';
            """
            data = await connection.fetch(query, guild.id, nsfw)
        return [record["content"].lower() if flatten_case else record["content"] for record in data]


class Message_Attachments(Table, schema="logging"):  # type: ignore
    message_id: SQLType.BigInt = Column(primary_key=True, references=Message_Log.message_id)
    attachment_id: SQLType.BigInt
    content: str


class Message_Edit_History(Table, schema="logging"):  # type: ignore
    message_id: SQLType.BigInt = Column(primary_key=True, references=Message_Log.message_id)
    created_at: SQLType.Timestamp = Column(primary_key=True)
    content: str


Status = enum("Status", "online offline idle dnd streaming")


class Status_Log(Table, schema="logging"):  # type: ignore
    user_id: SQLType.BigInt = Column(primary_key=True, index=True)
    timestamp: SQLType.Timestamp = Column(primary_key=True)
    status: Status  # type: ignore


class Opt_In_Status(Table, schema="logging"):  # type: ignore
    user_id: SQLType.BigInt = Column(primary_key=True, index=True)
    public: SQLType.Boolean = Column(default=False)
    nsfw: SQLType.Boolean = Column(default=False)

    @classmethod
    async def is_opted_in(cls, ctx: Context, *, connection: asyncpg.Connection = None):
        opt_in_status = await cls.fetchrow(connection=connection, user_id=ctx.author.id)
        if opt_in_status is None:
            raise commands.BadArgument(
                f"You have not opted in to logging. You can do so with `{ctx.bot.prefix}logging start`"
            )

    @classmethod
    async def is_not_opted_in(cls, ctx: Context, *, connection: asyncpg.Connection = None):
        opt_in_status = await cls.fetchrow(connection=connection, user_id=ctx.author.id)
        if opt_in_status is not None:
            raise commands.BadArgument("You have already opted into logging.")

    @classmethod
    async def is_public(cls, ctx: Context, user: discord.User, *, connection: asyncpg.Connection = None):
        opt_in_status = await cls.fetchrow(connection=connection, user_id=user.id)
        if opt_in_status is None:
            if user == ctx.author:
                raise commands.BadArgument(
                    f"You have not opted in to logging. You can do so with `{ctx.bot.prefix}logging start`"
                )
            else:
                raise commands.BadArgument(f'User "{user}" has not opted in to logging.')

        if user != ctx.author and not opt_in_status["public"]:
            raise commands.BadArgument(f'User "{user}" has not made their logs public.')
