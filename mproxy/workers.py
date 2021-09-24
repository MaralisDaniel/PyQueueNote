import abc
import asyncio
import aiohttp
import random
import logging

from .exceptions import ServerInitError, RequestExecutionError


CLIENT_TOTAL_TIMEOUT = 30
CLIENT_CONN_TIMEOUT = 10
CLIENT_SOCK_TIMEOUT = 30
CLIENT_SOCK_READ_TIMEOUT = 300


DEFAULT_LOGGER_NAME = 'm-proxy.worker'
REGISTERED_WORKERS = {}


# Interface for any custom worker
class BaseWorker(abc.ABC):
    @abc.abstractmethod
    def prepare(self) -> None:
        pass

    @abc.abstractmethod
    async def operate(self, message: str) -> None:
        pass

    @abc.abstractmethod
    async def free(self) -> None:
        pass


class BaseHTTPWorker(BaseWorker):
    def __init__(self):
        self._session = None

    def prepare(self) -> None:
        timeout = aiohttp.ClientTimeout(
                CLIENT_TOTAL_TIMEOUT,
                CLIENT_TOTAL_TIMEOUT,
                CLIENT_CONN_TIMEOUT,
                CLIENT_SOCK_READ_TIMEOUT
        )

        self._session = aiohttp.ClientSession(timeout=timeout)

    @abc.abstractmethod
    async def operate(self, message: str) -> None:
        pass

    async def execute_query(self, url: str, method: str, data: dict = None) -> dict:
        async with self._session.request(method, url, data=data) as response:
            result = {'status': response.status}

            if response.content_type == 'application/json':
                result['data'] = await response.json()
            else:
                result['data'] = response.text()

            return result

    async def free(self) -> None:
        await self._session.close()


# Default workers
class Telegram(BaseHTTPWorker):
    def __init__(self, params: dict, channel: str, logger: logging.Logger = None) -> None:
        self.params = params
        self.channel = channel
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

        self._prepared = False
        self._url = None
        self._data = None

        super().__init__()

    def prepare(self) -> None:
        self._log.debug('Preparing worker %s', self.__class__.__name__)

        self._data = {
            'chat_id': self.params['chat_id'],
            'disable_notification': self.params.get('disable_notification', False)
        }

        if 'parse_mode' in self.params:
            self._data['parse_mode'] = self.params['parse_mode']

        host = self.params['host']

        if not host.startswith('http'):
            host = 'http://' + host

        self._url = f"{host.rstrip('/')}/bot{self.params['bot_id']}/sendMessage"

        self._prepared = True

        super().prepare()

        self._log.debug('Worker ready')

    async def operate(self, message: str) -> None:
        if not self._prepared:
            raise RequestExecutionError('Worker is not ready')

        self._log.debug('Perform request')
        response = await self.execute_query(self._url, 'POST', {'text': message, **self._data})

        # TODO add special errors raising in case of 400 and 503 errors
        if response['data'].get('ok', False):
            self._log.info(
                    'Channel %s accepted the message, its id: %d',
                    self.channel,
                    response['data']['result']['message_id']
            )
        else:
            self._log.warning(
                    'Channel %s declined the message, status: %d, reason: %s',
                    self.channel,
                    response['status'],
                    response['data'].get('description')
            )

    async def free(self) -> None:
        self._log.debug('Release worker')

        await super().free()

        self._prepared = False
        self._url = None
        self._data = None

        self._log.debug('Worker released')


class Stub(BaseWorker):
    def __init__(self, params: dict, channel: str, logger: logging.Logger = None) -> None:
        self.params = params
        self.channel = channel

        self._prepared = False
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)
        self._min_delay = None
        self._max_delay = None

    def prepare(self) -> None:
        self._log.debug('Preparing worker %s', self.__class__.__name__)

        self._min_delay = self.params.get('min_delay', 1)
        self._max_delay = self.params.get('max_delay', 5)

        self._prepared = True

        self._log.debug('Worker ready')

    async def operate(self, message: str) -> None:
        if not self._prepared:
            raise RequestExecutionError('Worker is not ready')

        delay = random.randint(self._min_delay, self._max_delay)

        self._log.debug('Sleeping for %d', delay)

        await asyncio.sleep(delay)

        # TODO add pseudo error to imitate outer server 400 and 503 errors

        self._log.info(f'After {delay} seconds "{message}" was sent to {self.channel}')

    async def free(self) -> None:
        self._log.debug('Release worker')

        self._min_delay = None
        self._max_delay = None

        self._prepared = False

        self._log.debug('Worker released')


def register_worker(worker: callable, name: str = None) -> None:
    if not issubclass(worker, BaseWorker):
        raise ServerInitError(
                f"Unable to register {worker.__name__} as worker - it doesn't implements {BaseWorker.__name__}"
        )

    name = name or worker.__name__

    if name in REGISTERED_WORKERS:
        raise ServerInitError(f'Worker {name} (or its alias) already registered')

    REGISTERED_WORKERS[name] = worker


def resolve_worker(name: str) -> callable:
    if name in REGISTERED_WORKERS:
        return REGISTERED_WORKERS[name]

    raise ServerInitError(f'Requested worker {name} is not registered')


register_worker(Stub)
register_worker(Telegram)

__all__ = ['resolve_worker', 'register_worker', 'BaseWorker']
