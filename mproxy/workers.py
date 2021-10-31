from __future__ import annotations

import contextlib
import logging

import aiohttp

from .exceptions import WorkerAwaitError, WorkerExecutionError
from .model import BaseMessage

CLIENT_TOTAL_TIMEOUT = 30
DEFAULT_LOGGER_NAME = 'm-proxy.worker'


# Interface for any custom worker
class WorkerType:
    async def operate(self, message: BaseMessage) -> None: ...
    @contextlib.asynccontextmanager
    async def prepare(self) -> WorkerType: ...


class BaseHTTPWorker:
    def __init__(self, url: str, method: str) -> None:
        self._url = url
        self._method = method
        self._timeout = aiohttp.ClientTimeout(CLIENT_TOTAL_TIMEOUT)
        self._session = None

    async def operate(self, message: BaseMessage) -> None:
        raise NotImplementedError()

    @contextlib.asynccontextmanager
    async def prepare(self) -> BaseHTTPWorker:
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            self._session = session
            yield self
            self._session = None

    async def execute_query(self, data: dict = None) -> dict:
        async with self._session.request(self._method, self._url, data=data) as response:
            result = {'status': response.status, 'retry-after': response.headers.get('Retry-After')}
            if response.content_type == 'application/json':
                result['data'] = await response.json()
                return result
            result['data'] = await response.text()
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

    RETRY_CODES = (408, 502, 503, 504)

    def __init__(self, channel: str, url: str, chat_id: int, bot_id: str, logger: logging.Logger = None) -> None:
        super().__init__(f"{url.rstrip('/')}/bot{bot_id}/sendMessage", 'POST')
        self.channel = channel
        self._data = {'chat_id': chat_id}
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    async def operate(self, message: BaseMessage) -> None:
        response = await self.execute_query({'text': message.message, **message.params, **self._data})
        result = response['data'] if isinstance(response['data'], dict) else {'origin': response['data']}
        if result.get('ok'):
            self._log.info('Channel %s accepted the message, its id: %d', self.channel, response['data']['result']['message_id'])
            return
        reason = result.get('description', f"Not specified, code: {response['status']}")
        if response['status'] in self.RETRY_CODES:
            retry_after = result.get('retry_after', response['retry-after'])
            raise WorkerAwaitError(response['status'], reason, delay=retry_after)
        raise WorkerExecutionError(response['status'], reason)
