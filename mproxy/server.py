import logging
import typing
from aiohttp import web

from .exceptions import RequestParameterError, TemporaryUnawailableError
from .vchannel import Message, VirtualChannel


DEFAULT_RETRY_AFTER = 120
MAINTENANCE_KEY = 'maintenance'
DEFAULT_LOGGER_NAME = 'm-proxy.server'


class Application:
    def __init__(
            self,
            queues: dict,
            workers: dict,
            *,
            host: str,
            port: int,
            config: dict,
            debug: bool,
            retry_after: int = DEFAULT_RETRY_AFTER,
            logger: logging.Logger = None
    ) -> None:
        self.inited = False

        logging.basicConfig(
                level=logging.DEBUG if debug else logging.INFO,
                format='%(asctime)s - %(levelname)s, %(name)s: %(message)s',
        )

        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

        self._log.info('Initializing components')

        self.app = web.Application()
        self.host = host
        self.port = port
        self.retry_after = int(retry_after)

        self._components = {'queues': queues, 'workers': workers}

        self.config = config
        self.channels = {}

        self.app[MAINTENANCE_KEY] = True

    def prepare(self) -> None:
        self._log.debug('Setting routing and middlewares')

        self.app.middlewares.append(self.handle_errors_middleware)
        self.app.router.add_route('GET', '/api/ping', self.ping)
        self.app.router.add_route('POST', r'/api/send/{v_channel:[\w\-]{4,24}}', self.send_message)

        self._log.debug('Setting startup and shutdown events')
        self._log.debug('Preparing virtual channels configuration')

        for name, config in self.config.items():
            self._log.debug('Registering channel %s', name)
            self.channels[name] = VirtualChannel.create_from_config(name, config, self._components)

            self.app.on_startup.append(self.channels[name].activate)
            self.app.on_shutdown.append(self.channels[name].deactivate)

        self._log.info('Application is ready to operate')

        self.inited = True

    def run(self) -> None:
        self._log.debug('Starting app')

        self.app[MAINTENANCE_KEY] = False

        if not self.inited:
            raise RuntimeError('Application is not inited')

        self._log.debug('Run web app at %s:%d', self.host, self.port)

        web.run_app(self.app, host=self.host, port=self.port)

        self._log.debug('App terminated')

    async def send_message(self, request: web.Request) -> web.Response:
        channel = request.match_info.get('v_channel')
        self._log.debug('Channel selected: %s', channel)

        v_channel = self.channels.get(channel)

        if v_channel is None:
            self._log.warning('Request to unknown channel %s', channel)

            raise RequestParameterError(f'Unknown channel {channel}')

        if not v_channel.is_running:
            self._log.warning('Request in channel that is not active')

            raise TemporaryUnawailableError('Channel is not available for now')

        data = await request.post()

        delay = int(data.get('delay', '0'))
        self._log.debug('Request parameter delay is read: %s', delay)

        message = Message.extract_from_request_data(data)
        self._log.debug('Request parameter message is read: %s', message)

        v_channel.get_queue().add_task((message, delay))

        self._log.debug('Request completed')

        return web.json_response({'status': 'success'})

    async def ping(self, request: web.Request) -> web.Response:
        if request.app[MAINTENANCE_KEY]:
            return web.Response(status=503, text='FAIL', headers={'Retry-After': str(self.retry_after)})

        return web.Response(text='OK')

    @web.middleware
    async def handle_errors_middleware(self, request: web.Request, handler: typing.Callable) -> web.Response:
        try:
            return await handler(request)
        except RequestParameterError as e:
            return web.json_response({'status': 'error', 'error': str(e)}, status=422)
        except TemporaryUnawailableError as e:
            return web.json_response({'status': 'error', 'error': str(e)}, status=503)
        except web.HTTPException:
            raise
        except Exception as e:
            return web.json_response({'status': 'error', 'error': str(e)}, status=500)
