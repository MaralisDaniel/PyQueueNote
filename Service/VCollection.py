import asyncio
from Exceptions import ServiceException
from .Queues import Default
from .Workers import get_stub_worker


class VCollection:
    __channels = {}

    def __init__(self, config):
        for key, params in config.items():
            self.__add_channel(key, params)

    def add_task(self, channel, message):
        if channel not in self.__channels:
            raise ServiceException('Requested channel not found')

        asyncio.create_task(self.__channels[channel]['queue'].add_task(message))

    def get_pattern(self, channel):
        if channel not in self.__channels:
            raise ServiceException('Requested channel not found')

        return self.__channels[channel]['pattern']

    def is_channel(self, channel):
        return channel in self.__channels

    def __add_channel(self, channel, params):
        self.__channels[channel] = {}

        queue = Default()  # TODO change for dynamic queue type usage
        pattern, worker = get_stub_worker(params)  # TODO change for dynamic worker type usage

        # TODO move activation (task creation in asyncio) after app is run
        asyncio.get_event_loop().create_task(worker(queue))

        self.__channels[channel]['queue'] = queue
        self.__channels[channel]['pattern'] = pattern
