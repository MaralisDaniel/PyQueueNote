import asyncio
import logging

from .exceptions import TemporaryUnawailableError
from .model import Message

DEFAULT_LOGGER_NAME = 'm-proxy.queue'


# Interface for custom queues
class QueueInterface:
    def add_task(self, message: Message, delay: int = 0) -> None:
        raise NotImplementedError()

    async def get_task(self) -> Message:
        raise NotImplementedError()

    def current_items_count(self) -> int:
        raise NotImplementedError()


# Default queues
class AIOQueue(QueueInterface):
    def __init__(self, queue_size, logger: logging.Logger = None) -> None:
        self._queue_size = int(queue_size)

        self.queue = asyncio.Queue(maxsize=self._queue_size)

        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    def add_task(self, message: Message, delay: int = 0) -> None:
        try:
            self.queue.put_nowait(message)

            self._log.debug('Add message in queue')
        except asyncio.QueueFull:
            self._log.warning('Failed to add message in queue - queue is full')

            raise TemporaryUnawailableError('Queue of this channel is full. Try again later')

    async def get_task(self) -> Message:
        message = await self.queue.get()

        self.queue.task_done()

        self._log.debug('Message extracted from queue')

        return message

    def current_items_count(self) -> int:
        return self.queue.qsize()
