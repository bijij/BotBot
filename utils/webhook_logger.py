import asyncio
import aiohttp

from contextlib import suppress

from discord import AsyncWebhookAdapter, Embed, Webhook, HTTPException


class EmbedWebhookLogger:

    def __init__(self, webhool_url: str, *, loop: asyncio.BaseEventLoop = None):
        self.loop = loop or asyncio.get_event_loop()
        self._webhook_url = webhool_url
        self._to_log = list()
        self.loop.create_task(self._loop())

    def log(self, embed: Embed):
        self._to_log.append(embed)

    async def _loop(self):
        self._session = aiohttp.ClientSession()
        self._webhook = Webhook.from_url(self._webhook_url, adapter=AsyncWebhookAdapter(self._session))

        while True:

            with suppress(HTTPException):
                while self._to_log:
                    embeds = [self._to_log.pop(0) for _ in range(min(10, len(self._to_log)))]
                    await self._webhook.send(embeds=embeds)

            await asyncio.sleep(5)
