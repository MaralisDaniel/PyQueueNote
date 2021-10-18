import asyncio
import logging
import random

import mproxy

DEFAULT_LOGGER_NAME = 'stubs.worker'


class StubScenarioInterface:
    def __call__(self, message_id: str):
        raise NotImplementedError()

    def reset_scenario(self):
        raise NotImplementedError()


class Stub(mproxy.WorkerInterface):
    def __init__(
            self,
            channel: str,
            *,
            min_delay: int = 1,
            max_delay: int = 5,
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

    async def operate(self, message: mproxy.Message) -> None:
        delay = random.randint(self._min_delay, self._max_delay)
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
