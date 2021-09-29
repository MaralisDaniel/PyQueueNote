from __future__ import annotations
import asyncio
import logging
import tenacity

from .exceptions import RequestExecutionError, ServerInitError, WorkerAwaitError, WorkerExecutionError
from .model import Message
from .queues import BaseQueue, AIOQueue
from .workers import BaseWorker, Stub


DEFAULT_WORKER = Stub
DEFAULT_QUEUE = AIOQueue

DEFAULT_QUEUE_SIZE = 1000
DEFAULT_RETRY_AFTER_TIMEOUT = 30
DEFAULT_LOGGER_NAME = 'm-proxy.v-channel'

MIN_RETRY_AFTER = 5
MAX_RETRY_AFTER = 7200
RETRY_ATTEMPTS = 5


class IncrementOrRetryAfterWait(tenacity.wait.wait_base):
    def __init__(self, starts: int, ends: int, base: int = 4):
        self._starts = starts
        self._ends = ends
        self._base = base

    def __call__(self, retry_state: tenacity.RetryCallState):
        try:
            delay = retry_state.outcome.exception().get_delay_in_seconds()

            return min(delay, self._ends)
        except AttributeError:
            try:
                delay = self._starts + (self._base ** retry_state.attempt_number)
            except OverflowError:
                delay = self._ends

        return max(delay, self._ends)


class VirtualChannel:
    def __init__(
            self,
            name,
            worker: BaseWorker,
            queue: BaseQueue,
            *,
            logger: logging.Logger = None,
            min_retry_after: int = MIN_RETRY_AFTER,
            max_retry_after: int = MAX_RETRY_AFTER,
            retry_attempts: int = MIN_RETRY_AFTER,
    ) -> None:
        if not isinstance(worker, BaseWorker) or not isinstance(queue, BaseQueue):
            raise ServerInitError('Worker or Queue should implement correct base class')

        self.min_retry_after = min_retry_after
        self.max_retry_after = max_retry_after
        self.retry_attempts = retry_attempts
        self.name = name
        self.worker = worker
        self.queue = queue
        self.task = None
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    def get_queue(self) -> BaseQueue:
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

    async def assign_worker(self):
        while True:
            try:
                asyncio.create_task(self.send_with_delay(*(await self.queue.get_task())))
            except asyncio.CancelledError:
                self._log.info(f'Operation of worker in {self.name} was stopped')

                break
            except Exception as e:
                self._log.warning('Exception raised in %s worker operating cycle: %s', self.name, str(e))

    async def send_with_delay(self, message: Message, delay: int):
        await asyncio.sleep(delay)

        @tenacity.retry(
                stop=tenacity.stop_after_attempt(self.retry_attempts),
                wait=IncrementOrRetryAfterWait(self.min_retry_after, self.max_retry_after),
                retry=tenacity.retry_if_exception_type(WorkerAwaitError),
                reraise=True,
        )
        async def execute():
            await self.worker.operate(message)

        try:
            await execute()
        except asyncio.CancelledError:
            self._log.info('Retry cycle in %s worker was interrupted, task aborted', self.name)
        except WorkerExecutionError as e:
            self._log.error('Request in %s is rejected: %s', self.name, str(e))
        except WorkerAwaitError as e:
            self._log.warning('Request in %s has failed: %s', self.name, str(e))
        except Exception as e:
            self._log.warning('Unknown exception type raised in %s, %s', self.name, str(e))

    @classmethod
    def create_from_config(cls, name: str, config: dict, app_components: dict) -> VirtualChannel:
        worker_class = app_components['workers'].get(config.get('worker'), DEFAULT_WORKER)
        queue_class = app_components['queues'].get(config.get('queue'), DEFAULT_QUEUE)

        return cls(
                name,
                worker_class(name, **config.get('params', {})),
                queue_class(
                        config.get('queue_size', DEFAULT_QUEUE_SIZE),
                        config.get('queue_full_timeout', DEFAULT_RETRY_AFTER_TIMEOUT),
                ),
        )

    @property
    def is_running(self):
        return self.task is not None and not self.task.done()

    def __repr__(self):
        state = 'idle' if self.task is None else 'running'

        return f'Virtual channel {self.name}, state {state}'
