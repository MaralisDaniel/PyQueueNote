import logging
import typing

import aiohttp

from .exceptions import WorkerAwaitError, WorkerExecutionError
from .model import Message

CLIENT_TOTAL_TIMEOUT = 30
DEFAULT_LOGGER_NAME = 'm-proxy.worker'


# Interface for any custom worker
class WorkerInterface:
    async def operate(self, message: Message) -> None:
        raise NotImplementedError()


class BaseHTTPWorker(WorkerInterface):
    def __init__(self, url: str, method: str) -> None:
        self._url = url
        self._method = method
        self._timeout = aiohttp.ClientTimeout(CLIENT_TOTAL_TIMEOUT)

    async def operate(self, message: Message) -> None:
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
    def __init__(
            self,
            channel: str,
            *,
            url: str,
            chat_id: int,
            bot_id: str,
            no_notify: bool = False,
            parse_mode: str = None,
            logger: logging.Logger = None,
    ) -> None:
        super().__init__(f"{url.rstrip('/')}/bot{bot_id}/sendMessage", 'POST')

        self.channel = channel

        self._data = {
            'chat_id': chat_id,
            'disable_notification': no_notify,
        }  # type: dict[str, typing.Union[str, int, bool]]

        if parse_mode is not None and len(parse_mode) > 0:
            self._data['parse_mode'] = parse_mode

        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    async def operate(self, message: Message) -> None:
        self._log.debug('Perform request')
        response = await self.execute_query({'text': message.text, **self._data})

        if response['data'].get('ok', False):
            self._log.info(
                    'Channel %s accepted the message, its id: %d',
                    self.channel,
                    response['data']['result']['message_id'],
            )
        else:
            reason = response.get('data', {}).get('description')

            self._log.warning(
                    'Channel %s declined the message, status: %d, reason: %s',
                    self.channel,
                    response['status'],
                    reason,
            )

            if response['status'] == 503:
                retry_after = response.get('data', {}).get('retry_after', response['retry-after'])

                raise WorkerAwaitError(503, reason, retry_after)

            raise WorkerExecutionError(response['status'], reason)
