from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import uuid
from typing import Union

import mproxy

DEFAULT_LOGGER_NAME = 'stubs.worker'


class StubScenarioInterface:
    def __call__(self, message_id: uuid.UUID):
        raise NotImplementedError()

    def reset_scenario(self):
        raise NotImplementedError()


class Stub:
    """
    Stub worker is a testing instrument - it allows you to test service and watch for worker activity in logs
    It is expecting next params (optional, may be listed in 'params' array in the config file):
        min_delay - minimal amount of seconds before emulate message delivery
        max_delay - maximum amount of seconds before emulate message delivery
        delay_chance - chance that message delivery will fail and it is possible to retry it
        error_chance - chance that message delivery will fail and it is useless to retry it
    """

    def __init__(
            self,
            channel: str,
            min_delay: Union[int, float] = 1,
            max_delay: Union[int, float] = 5,
            delay_chance: int = 20,
            error_chance: int = 5,
            scenario: StubScenarioInterface = None,
            reset_scenario: bool = False,
            logger: logging.Logger = None,
    ) -> None:
        self.channel = channel
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._error_chance = error_chance
        self._delay_chance = delay_chance
        self.scenario = scenario
        self.reset_scenario = reset_scenario
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    @contextlib.asynccontextmanager
    async def prepare(self) -> Stub:
        yield self

    async def operate(self, message: mproxy.BaseMessage) -> None:
        delay = random.uniform(self._min_delay, self._max_delay)
        coin = random.randint(0, 100)
        self._log.debug('Sleeping for %d', delay)
        if self.scenario is not None:
            try:
                delay, coin = self.scenario(message.id)
            except StopIteration:
                if self.reset_scenario:
                    self.scenario.reset_scenario()
                    delay, coin = self.scenario(message.id)
        await asyncio.sleep(delay)
        if coin <= self._error_chance:
            self._log.info(f'After {delay} seconds "{message}" was rejected by {self.channel}')
            raise mproxy.WorkerExecutionError(400, 'Emulate error in request processing')
        elif coin <= self._delay_chance:
            self._log.info(f'After {delay} seconds "{message}" take too long to accept by {self.channel}')
            raise mproxy.WorkerAwaitError(503, 'Emulate error in request processing')
        self._log.info(f'After {delay} seconds "{message}" was sent to {self.channel}')
