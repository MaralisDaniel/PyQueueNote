import asyncio
from Exceptions import ServiceException
from .Queues import Default
import Service.Workers


class VCollection:
    __channels = {}

    def __init__(self, config: dict) -> None:
        for key, params in config.items():
            self.__add_channel(key, params)

    def add_task(self, channel: str, message: str) -> None:
        if channel not in self.__channels:
            raise ServiceException('Requested channel not found')

        asyncio.create_task(self.__channels[channel]['queue'].add_task(message))

    def get_pattern(self, channel: str) -> str:
        if channel not in self.__channels:
            raise ServiceException('Requested channel not found')

        return self.__channels[channel]['pattern']

    def is_channel(self, channel: str) -> bool:
        return channel in self.__channels

    def __add_channel(self, channel: str, params: dict) -> None:
        self.__channels[channel] = {}

        queue = Default()  # TODO change for dynamic queue type usage

        # TODO change for dynamic worker type usage
        if channel == 'telegram':
            pattern, worker = Service.Workers.telegram.get_worker(channel, params)
        else:
            pattern, worker = Service.Workers.stub.get_worker(channel, params)

        # TODO move activation (task creation in asyncio) after app is run
        asyncio.get_event_loop().create_task(worker(queue))

        self.__channels[channel]['queue'] = queue
        self.__channels[channel]['pattern'] = pattern
