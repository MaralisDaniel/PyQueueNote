import logging
import typing

from aiohttp import web

from .exceptions import RequestParameterError, TemporaryUnawailableError
from .model import Message
from .vchannel import VirtualChannel

DEFAULT_RETRY_AFTER = 120
DEFAULT_LOGGER_NAME = 'm-proxy.server'


class Application:
    MAINTENANCE_KEY = 'maintenance'

    def __init__(
            self,
            web_app: web.Application,
            queues: dict,
            workers: dict,
            *,
            host: str,
            port: int,
            config: dict,
            debug: bool,
            retry_after: int = None,
            logger: logging.Logger = None
    ) -> None:
        logging.basicConfig(
                level=logging.DEBUG if debug else logging.INFO,
                format='%(asctime)s - %(levelname)s, %(name)s: %(message)s',
        )

        self._log_type = logger
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

        self._log.info('Initializing application')

        self.app = web_app
        self.host = host
        self.port = port
        self.retry_after = DEFAULT_RETRY_AFTER if retry_after is None else int(retry_after)

        self._components = {'queues': queues, 'workers': workers}

        self.config = config
        self.channels = {}

        self.app[Application.MAINTENANCE_KEY] = True

    def prepare(self) -> None:
        self._log.debug('Setting routing and middlewares')

        self.app.middlewares.append(self.handle_errors_middleware)
        self.app.router.add_route('GET', '/api/ping', self.ping)
        self.app.router.add_route('POST', r'/api/send/{v_channel:[\w\-]{4,24}}', self.send_message)

        self._log.debug('Setting startup and shutdown events')
        self._log.debug('Preparing virtual channels configuration')

        for name, channel_config in self.config.items():
            self._log.debug('Registering channel %s', name)
            self.channels[name] = VirtualChannel.create_from_config(
                    name,
                    channel_config,
                    self._components,
                    logger=self._log_type,
            )

            self.app.on_startup.append(self.channels[name].activate)
            self.app.on_shutdown.append(self.channels[name].deactivate)

        self._log.info('Application is ready to operate')

    def run(self) -> None:
        self._log.debug('Starting app')

        self.app[Application.MAINTENANCE_KEY] = False

        self._log.debug('Run web app at %s:%d', self.host, self.port)

        web.run_app(self.app, host=self.host, port=self.port)

        self._log.debug('App terminated')

    async def send_message(self, request: web.Request) -> web.Response:
        if request.app[Application.MAINTENANCE_KEY]:
            raise TemporaryUnawailableError('Service is temporary unawailable')

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
        self._log.debug('Request parameter delay is read: %d', delay)

        message = Message.extract_from_request_data(data)
        self._log.debug('Request parameter message is read: %s', message)

        v_channel.get_queue().add_task(message, delay)

        self._log.debug('Request completed')

        return web.json_response({'status': 'success'})

    async def ping(self, request: web.Request) -> web.Response:
        if request.app[Application.MAINTENANCE_KEY]:
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
