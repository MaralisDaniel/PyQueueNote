import logging

import aiohttp

from .exceptions import WorkerAwaitError, WorkerExecutionError
from .model import BaseMessage

CLIENT_TOTAL_TIMEOUT = 30
DEFAULT_LOGGER_NAME = 'm-proxy.worker'


# Interface for any custom worker
class WorkerInterface:
    async def operate(self, message: BaseMessage) -> None: ...


class BaseHTTPWorker:
    def __init__(self, url: str, method: str) -> None:
        self._url = url
        self._method = method
        self._timeout = aiohttp.ClientTimeout(CLIENT_TOTAL_TIMEOUT)

    async def operate(self, message: BaseMessage) -> None:
        raise NotImplementedError()

    async def execute_query(self, data: dict = None) -> dict:
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.request(self._method, self._url, data=data) as response:
                result = {'status': response.status, 'retry-after': response.headers.get('Retry-After')}

                if response.content_type == 'application/json':
                    result['data'] = await response.json()
                else:
                    result['data'] = response.text()

                return result


# Default workers
class Telegram(BaseHTTPWorker):
    """
    Telegram worker performs requests to Telegram API (sendMessage method)
    It is expecting next params (must be listed in 'worker' array in the config file):
        url - host or domain name of Telegram API server (allows you to use worker with local API server)
        bot_id - id of the bot you are using to send messages (this id you will receive after Telegram bot is created)
        chat_id - id of chat where to send message (your bot must be in this chat)
    """

    def __init__(
            self,
            channel: str,
            *,
            url: str,
            chat_id: int,
            bot_id: str,
            logger: logging.Logger = None,
    ) -> None:
        super().__init__(f"{url.rstrip('/')}/bot{bot_id}/sendMessage", 'POST')

        self.channel = channel

        self._data = {'chat_id': chat_id}

        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    async def operate(self, message: BaseMessage) -> None:
        response = await self.execute_query({'text': message.message, **message.params, **self._data})

        if response['data'].get('ok', False):
            self._log.info(
                    'Channel %s accepted the message, its id: %d',
                    self.channel,
                    response['data']['result']['message_id'],
            )
        else:
            reason = response.get('data', {}).get('description')

            if response['status'] == 503:
                retry_after = response.get('data', {}).get('retry_after', response['retry-after'])

                raise WorkerAwaitError(503, reason, retry_after)

            raise WorkerExecutionError(response['status'], reason)
