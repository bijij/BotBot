import datetime
import logging

from discord import Embed, Colour

from utils.webhook_logger import EmbedWebhookLogger


ZWSP = '\N{ZERO WIDTH SPACE}'


class WebhookHandler(logging.Handler):
    _colours = {
        logging.DEBUG: Colour.light_grey(),
        logging.INFO: Colour.gold(),
        logging.WARNING: Colour.orange(),
        logging.ERROR: Colour.red(),
        logging.CRITICAL: Colour.dark_red()
    }

    def __init__(self, webhook_url, level=logging.NOTSET):
        super().__init__(level)
        self._webhook_logger = EmbedWebhookLogger(webhook_url)

    def emit(self, record: logging.LogRecord):
        self.format(record)

        message = f'{record.message}\n{record.exc_text or ""}'
        message = message[:1987] + '...' if len(message) > 1987 else message

        self._webhook_logger.log(
            Embed(
                colour=self._colours.get(record.levelno),
                title=record.name,
                description=f'```py\n{message}\n```',
                timestamp=datetime.datetime.fromtimestamp(record.created)
            ).add_field(
                name=ZWSP,
                value=f'{record.filename}:{record.lineno}'
            )
        )
