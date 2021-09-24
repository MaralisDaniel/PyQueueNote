import os
import yaml
import asyncio
import logging

import mproxy.queues
import mproxy.workers
from .exceptions import *


DEFAULT_WORKER = 'Stub'
DEFAULT_QUEUE = 'AIOQueue'
DEFAULT_QUEUE_SIZE = 100
DEFAULT_RETRY_AFTER_TIMEOUT = 120
DEFAULT_LOGGER_NAME = 'm-proxy.v-channel'


class VirtualChannel:
    def __init__(
            self,
            name,
            worker: mproxy.workers.BaseWorker,
            queue: mproxy.queues.BaseQueue,
            *,
            logger: logging.Logger = None
    ) -> None:
        if not isinstance(worker, mproxy.workers.BaseWorker) or not isinstance(queue, mproxy.queues.BaseQueue):
            raise ServerInitError('Worker or Queue should implement correct base class')

        self.name = name
        self.worker = worker
        self.queue = queue
        self.task = None
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    def get_queue(self) -> mproxy.queues.BaseQueue:
        return self.queue

    async def activate(self, web_app) -> None:
        if self.task is not None:
            raise RequestExecutionError('Virtual channel already is running')

        self._log.info('Activating %s virtual channel', self.name)

        self.worker.prepare()

        self.task = asyncio.create_task(self.assign_worker())

        self._log.debug('Channel active')

    async def deactivate(self, web_app) -> None:
        if self.task is None:
            raise RequestExecutionError('Virtual channel is not running')

        self._log.info('Deactivating %s virtual channel', self.name)

        self.task.cancel()

        self.task = None

        self.task = asyncio.create_task(self.worker.free())

        self._log.debug('Channel inactive')

    async def assign_worker(self):
        while True:
            try:
                message = await self.queue.get_task()

                await self.worker.operate(message)
            except Exception as e:
                # TODO add correct exception handling with retrying by tenacity
                self._log.warning('Exception has occurred in worker operating cycle: %s', str(e))

    @property
    def is_running(self):
        return self.task is not None and not self.task.done()

    def __repr__(self):
        state = 'idle' if self.task is None else 'running'

        return f'Virtual channel {self.name}, state {state}'


class ConfigReader:
    def __init__(self, file_name: str, strict: bool = True, *, logger: logging.Logger = None) -> None:
        self.file = os.path.abspath(os.path.join(os.getcwd(), file_name))
        self.config = None
        self.strict = strict
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    def read(self) -> None:
        self._log.debug('Reading configuration file %s', self.file)

        try:
            with open(self.file, 'r') as file:
                self.config = yaml.safe_load(file)

                file.close()
        except Exception as e:
            if self.strict:
                raise ServerInitError(f'Failed to read config file, reason: {str(e)}')

            self._log.warning('Config reading failed: %s, continue anyway')

            self.config = {}

    def reset(self, new_file_name: str) -> None:
        self._log.debug('Resetting configuration')

        self.config = None
        self.file = os.path.abspath(os.path.join(os.getcwd(), new_file_name))

    def get_config(self) -> dict:
        if self.config is None:
            raise ServerInitError('Config not read yet')

        return self.config


class VCCollection:
    def __init__(self, config_reader: ConfigReader, *, logger: logging.Logger = None) -> None:
        self.channels = {}
        self.config_reader = config_reader
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    def load_channels(self) -> None:
        vc_config = self.config_reader.get_config()

        for name, config in vc_config.items():
            self.add_channel(
                    name,
                    config.get('params', {}),
                    config.get('worker', DEFAULT_WORKER),
                    config.get('queue', DEFAULT_QUEUE),
                    config.get('queue_size', DEFAULT_QUEUE_SIZE),
                    config.get('queue_full_timeout', DEFAULT_RETRY_AFTER_TIMEOUT),
            )

    def get_channel(self, name: str) -> VirtualChannel:
        return self.channels[name]

    def is_channel(self, name: str) -> bool:
        return name in self.channels

    def add_channel(
            self,
            name: str,
            params: dict,
            worker: str,
            queue: str,
            queue_size: int,
            queue_full_timeout: int,
    ) -> None:
        self._log.debug('Attempting to add channel %s', name)

        worker_class = mproxy.workers.resolve_worker(worker)
        self._log.debug('Worker %s found', worker)

        queue_class = mproxy.queues.resolve_queue(queue)
        self._log.debug('Queue %s found', queue)

        self.channels[name] = VirtualChannel(
                name,
                worker_class(params, name),
                queue_class(queue_size, queue_full_timeout)
        )


__all__ = ['VCCollection', 'ConfigReader', 'VirtualChannel']
