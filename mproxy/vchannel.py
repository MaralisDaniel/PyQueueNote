from __future__ import annotations

import asyncio
import logging
import typing

import tenacity

from .exceptions import RequestExecutionError, ServerInitError, WorkerAwaitError, WorkerExecutionError
from .model import Message
from .queues import AIOQueue, QueueInterface
from .workers import Telegram, WorkerInterface

DEFAULT_WORKER = Telegram
DEFAULT_QUEUE = AIOQueue

DEFAULT_QUEUE_SIZE = 1000
DEFAULT_LOGGER_NAME = 'm-proxy.v-channel'

MIN_RETRY_AFTER = 5
MAX_RETRY_AFTER = 7200
RETRY_ATTEMPTS = 5
RETRY_BASE = 4


class IncrementOrRetryAfterWait(tenacity.wait.wait_base):
    def __init__(self, starts: int, ends: int, base: int = 4) -> None:
        self._starts = starts
        self._ends = ends
        self._base = base

    def __call__(self, retry_state: tenacity.RetryCallState) -> int:
        try:
            delay = retry_state.outcome.exception().get_delay_in_seconds()

            if delay == 0:
                raise AttributeError('Delay should not be 0')
        except AttributeError:
            try:
                delay = self._starts + (self._base ** retry_state.attempt_number)
            except OverflowError:
                delay = self._ends

        return min(delay, self._ends)


class VirtualChannel:
    def __init__(
            self,
            name,
            worker: WorkerInterface,
            queue: QueueInterface,
            *,
            logger: logging.Logger = None,
            min_retry_after: int = None,
            max_retry_after: int = None,
            retry_attempts: int = None,
            retry_base: int = None,
    ) -> None:
        if not isinstance(worker, WorkerInterface) or not isinstance(queue, QueueInterface):
            raise ServerInitError('Worker or Queue should implement correct interface')

        self.min_retry_after = MIN_RETRY_AFTER if min_retry_after is None else min_retry_after
        self.max_retry_after = MAX_RETRY_AFTER if max_retry_after is None else max_retry_after
        self.retry_attempts = RETRY_ATTEMPTS if retry_attempts is None else retry_attempts
        self.retry_base = RETRY_BASE if retry_base is None else retry_base
        self.name = name
        self.worker = worker
        self.queue = queue
        self.task = None  # type: typing.Union[None, asyncio.Task]

        self._log_type = logger
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    def get_queue(self) -> QueueInterface:
        return self.queue

    async def activate(self, *args) -> None:
        if self.task is not None:
            raise RequestExecutionError('Virtual channel already is running')

        self._log.info('Activating %s virtual channel', self.name)

        self.task = asyncio.create_task(self.assign_worker())
        self._log.debug('Channel active')

    async def deactivate(self, *args) -> None:
        if self.task is None:
            raise RequestExecutionError('Virtual channel is not running')

        self._log.info('Deactivating %s virtual channel', self.name)

        self.task.cancel()

        self.task = None

        self._log.debug('Channel inactive')

    async def assign_worker(self) -> None:
        @tenacity.retry(
                stop=tenacity.stop_after_attempt(self.retry_attempts),
                wait=IncrementOrRetryAfterWait(self.min_retry_after, self.max_retry_after, self.retry_base),
                retry=tenacity.retry_if_exception_type(WorkerAwaitError),
                reraise=True,
        )
        async def execute(message: Message):
            await self.worker.operate(message)

        while True:
            try:
                await execute(await self.queue.get_task())
            except asyncio.CancelledError:
                self._log.info(f'Execution of worker in {self.name} was stopped')

                break
            except WorkerExecutionError as e:
                self._log.error('Request in %s is rejected: %s', self.name, repr(e))
            except WorkerAwaitError as e:
                self._log.warning('Request in %s has failed: %s', self.name, repr(e))
            except Exception as e:
                self._log.warning(
                        'Unknown exception is raised in %s worker operating cycle: %s, %s',
                        self.name,
                        e.__class__.__name__,
                        repr(e),
                )

    @classmethod
    def create_from_config(
            cls,
            name: str,
            config: dict,
            app_components: dict,
            *,
            logger: logging.Logger = None
    ) -> VirtualChannel:
        worker_class = app_components['workers'].get(config.get('worker'), DEFAULT_WORKER)
        queue_class = app_components['queues'].get(config.get('queue'), DEFAULT_QUEUE)

        return cls(
                name,
                worker_class(name, **{**config.get('params', {}), 'logger': logger}),
                queue_class(config.get('queue_size', DEFAULT_QUEUE_SIZE), logger=logger),
                min_retry_after=config.get('minRetryAfter'),
                max_retry_after=config.get('maxRetryAfter'),
                retry_attempts=config.get('maxAttempts'),
                retry_base=config.get('retryBase'),
                logger=logger,
        )

    @property
    def is_running(self) -> bool:
        return self.task is not None and not self.task.done()

    def __repr__(self) -> str:
        state = 'idle' if self.task is None else 'running'

        return f'Virtual channel {self.name}, state {state}'
