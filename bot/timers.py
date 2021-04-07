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

from typing import Optional, Protocol, cast

import discord
from discord.ext import commands

import asyncpg

from donphan import Column, SQLType, Table


class Timers(Table, schema='core'):  # type: ignore
    id: SQLType.Serial = Column(primary_key=True)  # type: ignore
    created_at: SQLType.Timestamp = Column(default='NOW() AT TIME ZONE \'UTC\'')  # type: ignore
    expires_at: SQLType.Timestamp = Column(index=True)  # type: ignore
    event_type: str = Column(nullable=False, index=True)  # type: ignore
    data: SQLType.JSONB = Column(default='\'{}\'::jsonb')  # type: ignore

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

    async def call(self, bot: commands.Bot):
        if self.id is None:
            await discord.utils.sleep_until(self.expires_at)
        else:
            await Timers.delete(id=self.id)
        self.dispatch_event(bot)


class TimerBot(commands.Bot):
    _active_timer: asyncio.Event
    _current_timer: Optional[Timer]
    _timer_task: asyncio.Task


async def _get_active_timer(bot: TimerBot, *, connection: asyncpg.Connection = None, days: int = 7) -> Optional[Timer]:
    record = await Timers.fetchrow_where('expires_at < (CURRENT_DATE + $1::interval) ORDER BY expires_at ASC', datetime.timedelta(days=days))
    return Timer(record) if record else None


async def _wait_for_active(bot: TimerBot, *, days: int = 7) -> Timer:
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


async def dispatch_timers(bot: TimerBot):
    # Wait until bot is ready
    await bot.wait_until_ready()

    try:
        while not bot.is_closed():
            # fetch the next timer from the database
            timer = bot._current_timer = await _wait_for_active(bot, days=40)
            now = discord.utils.utcnow()

            # if timer has not yet expired
            if timer.expires_at >= now:
                await discord.utils.sleep_until(timer.expires_at)

            await timer.call(bot)

    except asyncio.CancelledError:
        pass
    except (OSError, discord.ConnectionClosed, asyncpg.exceptions.PostgresConnectionError):
        bot._timer_task.cancel()
        bot._timer_task = bot.loop.create_task(dispatch_timers(bot))
    except Exception as exc:
        print('Unhandled exception in internal timer task', file=sys.stderr)
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)


async def create_timer(bot: commands.Bot, expires_at: datetime.datetime, event_type: str, *args, **kwargs) -> Timer:
    bot = cast(TimerBot, bot)
    
    now = discord.utils.utcnow()
    timer = Timer.temporary(now, expires_at, event_type, *args, **kwargs)

    delta = (expires_at - now).total_seconds()
    if delta <= 60:
        bot.loop.create_task(timer.call(bot))
        return timer

    record = await Timers.insert(returning=Timers.id, expires_at=expires_at, event_type=event_type, data=dict(args=args, kwargs=kwargs))  # type: ignore

    # Set the timer's ID
    timer.id = record[0]

    bot._active_timer.set()

    # Check if the timer is earlier than the currently set timer
    if bot._current_timer is not None and expires_at < bot._current_timer.expires_at:
        bot._timer_task.cancel()
        bot._timer_task = bot.loop.create_task(dispatch_timers(bot))

    return timer


async def delete_timer(bot: commands.Bot, record: asyncpg.Record, *, connection: asyncpg.Connection):
    bot = cast(TimerBot, bot)
    
    await Timers.delete(id=record['id'])

    # if the current timer is being deleted skip it
    if bot._current_timer and bot._current_timer.id == record['id']:
        bot._timer_task.cancel()
        bot._timer_task = bot.loop.create_task(dispatch_timers(bot))
