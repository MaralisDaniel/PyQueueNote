import asyncio
import random
from ..Queues.AbstractQueue import AbstractQueue


def get_worker(channel: str, config: dict) -> callable:
    # TODO stub worker - replace later
    min_delay = config.get('minDelay', 1)
    max_delay = config.get('maxDelay', 5)

    pattern = '/[\\wа-я\\s]+/iu'

    async def worker(queue: AbstractQueue) -> None:
        while True:
            delay = random.randint(min_delay, max_delay)

            message = await queue.get_task()

            await asyncio.sleep(delay)

            print(f'After {delay} seconds "{message}" was sent to {channel}')

            queue.complete()

    return pattern, worker
