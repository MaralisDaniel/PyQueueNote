import abc
import asyncio
import logging

from .exceptions import TemporaryUnawailableError, ServerInitError

DEFAULT_LOGGER_NAME = 'm-proxy.queue'
REGISTERED_QUEUES = {}


# Interface for custom queues
class BaseQueue(abc.ABC):
    @abc.abstractmethod
    def add_task(self, message: str) -> None:
        pass

    @abc.abstractmethod
    async def get_task(self) -> str:
        pass

    @abc.abstractmethod
    def current_items(self) -> int:
        pass


# Default queues
class AIOQueue(BaseQueue):
    def __init__(self, queue_size: int, retry_after: int, *, logger: logging.Logger = None) -> None:
        self.queue = asyncio.Queue(queue_size)
        self.retry_after = retry_after
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    def add_task(self, message: str) -> None:
        try:
            self.queue.put_nowait(message)

            self._log.debug('Add message in queue')
        except asyncio.QueueFull:
            self._log.warning('Failed to add message in queue - queue is full')

            raise TemporaryUnawailableError('This queue is full. Try again later')

    async def get_task(self) -> str:
        message = await self.queue.get()

        self.queue.task_done()

        self._log.debug('Message extracted from queue')

        return message

    def current_items(self) -> int:
        return self.queue.qsize()


def register_queue(queue: callable, name: str = None) -> None:
    if not issubclass(queue, BaseQueue):
        raise ServerInitError(
                f"Unable to register {queue.__name__} as queue - it doesn't implements {BaseQueue.__name__}"
        )

    name = name or queue.__name__

    if name in REGISTERED_QUEUES:
        raise ServerInitError(f'Queue {name} (or its alias) already registered')

    REGISTERED_QUEUES[name] = queue


def resolve_queue(name: str) -> callable:
    if name in REGISTERED_QUEUES:
        return REGISTERED_QUEUES[name]

    raise ServerInitError(f'Requested queue {name} is not registered')


register_queue(AIOQueue)

__all__ = ['resolve_queue', 'register_queue', 'BaseQueue']
