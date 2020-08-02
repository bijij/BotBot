"""
The MIT License (MIT)

Copyright (c) 2015 Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

import asyncio
import datetime
import sys
import traceback

from typing import Optional

import discord
from discord.ext import commands

import asyncpg

from .db import ConnectionContext


class Timer:
    __slots__ = ('id', 'created_at', 'expires_at',
                 'event_type', 'args', 'kwargs')

    def __init__(self, record):
        self.id = record['id']
        self.created_at = record['created_at']
        self.expires_at = record['expires_at']
        self.event_type = record['event_type']
        data = record['data']
        self.args = data.get('args', [])
        self.kwargs = data.get('kwargs', {})

    @classmethod
    def temporary(cls, created_at, expires_at, event_type, *args, **kwargs):
        return cls(record={
            'id': None,
            'created_at': created_at,
            'expires_at': expires_at,
            'event_type': event_type,
            'data': {
                'args': args,
                'kwargs': kwargs
            }
        })

    def __eq__(self, other):
        try:
            return self.id == other.id
        except AttributeError:
            return False

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f'<Timer id={self.id} created_at={self.created_at} \
expires_at={self.expires_at} event_type={self.event_type}>'

    def dispatch_event(self, bot: commands.Bot):
        event_name = f'{self.event_type}_timer_complete'
        bot.dispatch(event_name, *self.args, **self.kwargs)

    async def call(self, bot: commands.Bot, *, connection: asyncpg.Connection = None):
        if self.id is None:
            await discord.utils.sleep_until(self.expires_at)
        else:
            async with ConnectionContext(connection=connection, pool=bot.pool) as connection:
                await connection.execute('DELETE FROM core.timers WHERE id = $1', self.id)
        self.dispatch_event(bot)


async def _get_active_timer(bot: commands.Bot, *, connection: asyncpg.Connection = None, days: int = 7) -> Optional[Timer]:
    async with ConnectionContext(connection=connection, pool=bot.pool) as connection:
        record = await connection.fetchrow('SELECT * FROM core.timers WHERE expires_at < (CURRENT_DATE + $1::interval)', datetime.timedelta(days=days))
        return Timer(record) if record else None


async def _wait_for_active(bot: commands.Bot, *, days: int = 7) -> Timer:
    # check for active timer
    timer = await _get_active_timer(bot, days=days)

    # if timer was found return it
    if timer is not None:
        bot._active_timer.set()
        return timer

    # otherwise wait for an active timer
    bot._active_timer.clear()
    bot._current_timer = None
    await bot._active_timer.wait()
    return await _wait_for_active(bot, days=days)


async def dispatch_timers(bot: commands.Bot):
    # Wait until bot is ready
    await bot.wait_until_ready()

    try:
        while not bot.is_closed():
            # fetch the next timer from the database
            timer = bot._current_timer = await _wait_for_active(bot, days=40)
            now = datetime.datetime.utcnow()

            # if timer has not yet expired
            if timer.expires_at >= now:
                await discord.utils.sleep_until(timer.expires_at)

            await timer.call(bot)

    except asyncio.CancelledError:
        pass
    except (OSError, discord.ConnectionClosed, asyncpg.PostgresConnectionError):
        bot._timer_task.cancel()
        bot._timer_task = bot.loop.create_task(dispatch_timers(bot))
    except Exception as exc:
        print('Unhandled exception in internal timer task', file=sys.stderr)
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)


async def create_timer(bot: commands.Bot, expires_at: datetime.datetime, event_type: str, *args, **kwargs) -> Timer:
    now = datetime.datetime.utcnow()
    timer = Timer.temporary(now, expires_at, event_type, *args, **kwargs)

    delta = (expires_at - now).total_seconds()
    if delta <= 60:
        bot.loop.create_task(timer.call(bot))
        return timer

    async with ConnectionContext(pool=bot.pool) as connection:
        record = await connection.fetchrow('INSERT INTO core.timers (expires_at, event_type, data)\
            VALUES ($1, $2, $3) RETURNING id', expires_at, event_type, dict(args=args, kwargs=kwargs))

    # Set the timer's ID
    timer.id = record[0]

    # Only set the data check if the timer can be waited for
    if delta <= discord.utils.MAX_ASYNCIO_SECONDS:
        bot._active_timer.set()

    # Check if the timer is earlier than the currently set timer
    if bot._current_timer and expires_at < bot._current_timer.expires_at:
        bot._timer_task.cancel()
        bot._timer_task = bot.loop.create_task(dispatch_timers(bot))

    return timer


async def delete_timer(bot: commands.Bot, record: asyncpg.Record, *, connection: asyncpg.Connection):
    async with ConnectionContext(connection=connection, pool=bot.pool) as connection:
        await connection.execute('DELETE FROM core.timers WHERE id = $1', record['id'])

    # if the current timer is being deleted skip it
    if bot._current_timer and bot._current_timer.id == record['id']:
        bot._timer_task.cancel()
        bot._timer_task = bot.loop.create_task(dispatch_timers(bot))
