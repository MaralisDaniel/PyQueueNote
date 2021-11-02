import asyncio
import logging

from .exceptions import TemporaryUnawailableError
from .model import BaseMessage

DEFAULT_LOGGER_NAME = 'm-proxy.queue'
DEFAULT_QUEUE_SIZE = 1000


# Interface for custom queues
class QueueType:
    def add_task(self, message: BaseMessage) -> None: ...
    async def get_task(self) -> BaseMessage: ...
    def current_items_count(self) -> int: ...


# Default queues
class AIOQueue:
    """
    Simple in-memory queue with no persistence at all
    It is expecting next params (optional, may be listed in 'queue' array in the config file):
        queue_size - size of used queue for this channel
    """

    def __init__(self, queue_size: int = DEFAULT_QUEUE_SIZE, logger: logging.Logger = None) -> None:
        self._queue_size = int(queue_size)
        self.queue = asyncio.Queue(maxsize=self._queue_size)  # type: asyncio.Queue
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    def add_task(self, message: BaseMessage) -> None:
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            self._log.error('Failed to add message in queue - queue is full')
            raise TemporaryUnawailableError('Queue of this channel is full. Try again later')

    async def get_task(self) -> BaseMessage:
        message = await self.queue.get()
        self.queue.task_done()
        return message

    def current_items_count(self) -> int:
        return self.queue.qsize()
