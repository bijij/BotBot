# Simplified version of ShellReader by Gorialis
# https://github.com/Gorialis/jishaku

import asyncio
import os
import re
import shlex
import subprocess
import sys
import time

SHELL = os.getenv("SHELL") or "/bin/bash"
IS_WINDOWS = sys.platform == 'win32'


def background_reader(stream, loop: asyncio.AbstractEventLoop, callback):
    """
    Reads a stream and forwards each line to an async callback.
    """

    for line in iter(stream.readline, b''):
        loop.call_soon_threadsafe(loop.create_task, callback(line))


class AsyncShell:
    def __init__(self, code: str, timeout: int = 90, loop: asyncio.AbstractEventLoop = None):

        if IS_WINDOWS:
            sequence = shlex.split(code)
        else:
            sequence = [SHELL, '-c', code]

        self.process = subprocess.Popen(sequence, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.exit_code = None

        self.timeout = timeout
        self.loop = loop or asyncio.get_event_loop()

        self.stdout_task = self.make_reader_task(self.process.stdout, self.stdout_handler)
        self.stderr_task = self.make_reader_task(self.process.stderr, self.stderr_handler)

        self.queue = asyncio.Queue(maxsize=250)

    async def executor_wrapper(self, *args, **kwargs):
        """
        Call wrapper for stream reader.
        """

        return await self.loop.run_in_executor(None, *args, **kwargs)

    def make_reader_task(self, stream, callback):
        """
        Create a reader executor task for a stream.
        """

        return self.loop.create_task(self.executor_wrapper(background_reader, stream, self.loop, callback))

    @staticmethod
    def clean_bytes(line):
        """
        Cleans a byte sequence of shell directives and decodes it.
        """

        text = line.decode('utf-8').replace('\r', '').strip('\n')
        return re.sub(r'\x1b[^m]*m', '', text).replace("``", "`\u200b`").strip('\n')

    async def stdout_handler(self, line):
        """
        Handler for this class for stdout.
        """

        await self.queue.put(self.clean_bytes(line))

    async def stderr_handler(self, line):
        """
        Handler for this class for stderr.
        """

        await self.queue.put(self.clean_bytes(b'[stderr] ' + line))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.process.kill()
        self.process.terminate()
        self.exit_code = self.process.wait(timeout=0.5)

    def __aiter__(self):
        return self

    async def __anext__(self):
        start = time.perf_counter()

        while not (self.stdout_task.done() and self.stderr_task.done()):
            try:
                return await asyncio.wait_for(self.queue.get(), timeout=1)
            except asyncio.TimeoutError as e:
                if time.perf_counter() - start >= self.timeout:
                    raise e

        raise StopAsyncIteration()
