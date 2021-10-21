from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import math
import typing

import tenacity

from .exceptions import RequestExecutionError, WorkerAwaitError, WorkerExecutionError
from .model import BaseMessage
from .queues import QueueInterface
from .workers import WorkerInterface

DEFAULT_LOGGER_NAME = 'm-proxy.v-channel'

MIN_RETRY_AFTER = 5
MAX_RETRY_AFTER = 7200
RETRY_ATTEMPTS = 5
RETRY_BASE = 4


def get_delay_in_seconds(delay: typing.Union[str, int, float]) -> int:
    try:
        delay_value = str(delay)

        if delay_value.endswith('GMT'):
            delay = datetime.strptime(delay_value, '%a, %d %b %Y %H:%M:%S %Z').timestamp()
            timestamp = datetime.now().timestamp()
        else:
            if delay_value.endswith('UTC'):
                delay_value = delay_value.replace('UTC', '+0000')

            delay = datetime.strptime(delay_value, '%a, %d %b %Y %H:%M:%S %z').timestamp()
            timestamp = datetime.now(timezone.utc).timestamp()

        return math.ceil(delay - timestamp)
    except ValueError:
        return int(delay)
    except Exception:
        raise


class WaitExponentialOrByRetryAfterValue(tenacity.wait.wait_base):
    def __init__(self, starts: int, ends: int, base: int = 4) -> None:
        self._starts = starts
        self._ends = ends
        self._base = base

    def __call__(self, retry_state: tenacity.RetryCallState) -> typing.Union[int, float]:
        exception = retry_state.outcome.exception()  # type: typing.Union[None, WorkerAwaitError]

        if not exception:
            raise RecursionError('Unclassified retry state')

        delay = self.calculate_delay(retry_state.attempt_number)

        if exception.delay:
            try:
                outer_delay = get_delay_in_seconds(exception.delay)

                if outer_delay >= 0:
                    delay = outer_delay
            except AttributeError:
                pass

        return min(delay, self._ends)

    def calculate_delay(self, rate: int) -> typing.Union[int, float]:
        try:
            return self._starts + (self._base ** rate)
        except OverflowError:
            return self._ends


class VirtualChannel:
    def __init__(
            self,
            name: str,
            worker: WorkerInterface,
            queue: QueueInterface,
            *,
            min_retry_after: int,
            max_retry_after: int,
            retry_attempts: int,
            retry_base: int,
            logger: logging.Logger = None,
    ) -> None:
        self._min_retry_after = MIN_RETRY_AFTER if min_retry_after is None else min_retry_after
        self._max_retry_after = MAX_RETRY_AFTER if max_retry_after is None else max_retry_after
        self._retry_attempts = RETRY_ATTEMPTS if retry_attempts is None else retry_attempts
        self._retry_base = RETRY_BASE if retry_base is None else retry_base
        self._name = name
        self._worker = worker
        self._queue = queue
        self._task = None  # type: typing.Union[None, asyncio.Task]

        self._messages_send = 0
        self._messages_rejected = 0
        self._last_error = None

        self._log_type = logger
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    def add_message(self, message: BaseMessage) -> None:
        self._queue.add_task(message)

    async def activate(self, *args) -> None:
        if self._task is not None and not self._task.done():
            raise RequestExecutionError('Virtual channel already is running')

        self._log.info('Activating %s virtual channel', self._name)

        self._task = asyncio.create_task(self.assign_worker())

        self._messages_send = 0
        self._messages_rejected = 0
        self._last_error = None

    async def deactivate(self, *args) -> None:
        if self._task is None:
            return

        self._log.info('Deactivating %s virtual channel', self._name)

        self._task.cancel()

        self._task = None

    async def assign_worker(self) -> None:
        @tenacity.retry(
                stop=tenacity.stop_after_attempt(self._retry_attempts),
                wait=WaitExponentialOrByRetryAfterValue(self._min_retry_after, self._max_retry_after, self._retry_base),
                retry=tenacity.retry_if_exception_type(WorkerAwaitError),
                reraise=True,
        )
        async def execute(message: BaseMessage):
            await self._worker.operate(message)

        while True:
            try:
                task = await self._queue.get_task()

                await execute(task)

                self._messages_send += 1
            except asyncio.CancelledError:
                self._log.info(f'Execution of worker in {self._name} was stopped')
                self._set_last_error('Worker was stopped')

                break
            except WorkerExecutionError as e:
                self._set_last_error(repr(e))
                self._messages_rejected += 1

                self._log.error('Request in %s is rejected: %s', self._name, repr(e))
            except WorkerAwaitError as e:
                self._set_last_error(repr(e))
                self._messages_rejected += 1

                self._log.error('Request in %s has failed: %s', self._name, repr(e))
            except Exception as e:
                self._set_last_error(repr(e))
                self._messages_rejected += 1

                self._log.error(
                        'Unknown exception is raised in %s worker operating cycle: %s, %s',
                        self._name,
                        e.__class__.__name__,
                        repr(e),
                )

                raise e

    def get_state(self):
        return {
            'was_send': self._messages_send,
            'was_rejected': self._messages_rejected,
        }

    def get_last_error(self, clear=False):
        error = self._last_error

        if clear:
            self._last_error = None

        return error

    def _set_last_error(self, reason):
        self._last_error = {
            'reason': reason,
            'stamp': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
        }

    @classmethod
    def create_from_config(
            cls,
            name: str,
            config: dict,
            app_components: dict,
            *,
            logger: logging.Logger = None
    ) -> VirtualChannel:
        worker_config = config['worker']
        queue_config = config['queue']

        worker_class = app_components['workers'][worker_config.pop('name')]
        queue_class = app_components['queues'][queue_config.pop('name')]

        return cls(
                name,
                worker_class(name, **{**worker_config, 'logger': logger}),
                queue_class(**{**queue_config, 'logger': logger}),
                min_retry_after=config.get('minRetryAfter', MIN_RETRY_AFTER),
                max_retry_after=config.get('maxRetryAfter', MAX_RETRY_AFTER),
                retry_attempts=config.get('maxAttempts', RETRY_ATTEMPTS),
                retry_base=config.get('retryBase', RETRY_BASE),
                logger=logger,
        )

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def __repr__(self) -> str:
        state = 'idle' if self._task is None else 'running'

        return f'Virtual channel {self._name}, state {state}'
