import asyncio
import logging
import random
import typing

import mproxy


DEFAULT_LOGGER_NAME = 'stubs.worker'


class Stub(mproxy.WorkerInterface):
    def __init__(
            self,
            channel: str,
            *,
            min_delay: int = 1,
            max_delay: int = 5,
            delay_chance: int = 20,
            error_chance: int = 5,
            coin_scenario: typing.Iterator = None,
            delay_scenario: typing.Iterator = None,
            logger: logging.Logger = None,
    ) -> None:
        self.channel = channel

        self._min_delay = min_delay
        self._max_delay = max_delay
        self._error_chance = error_chance
        self._delay_chance = delay_chance
        self.coin_scenario = coin_scenario
        self.delay_scenario = delay_scenario

        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    async def operate(self, message: mproxy.Message) -> None:
        delay = random.randint(self._min_delay, self._max_delay)
        coin = random.randint(0, 100)

        self._log.debug('Sleeping for %d', delay)

        if self.coin_scenario is not None:
            try:
                coin = next(self.coin_scenario)
            except StopIteration:
                pass

        if self.delay_scenario is not None:
            try:
                delay = next(self.delay_scenario)
            except StopIteration:
                pass

        await asyncio.sleep(delay)

        if coin <= self._error_chance:
            self._log.info(f'After {delay} seconds "{message}" was rejected by {self.channel}')

            raise mproxy.WorkerExecutionError(400, 'Emulate error in request processing')
        elif coin <= self._delay_chance:
            self._log.info(f'After {delay} seconds "{message}" take too long to accept by {self.channel}')

            raise mproxy.WorkerAwaitError(503, 'Emulate error in request processing')

        self._log.info(f'After {delay} seconds "{message}" was sent to {self.channel}')
