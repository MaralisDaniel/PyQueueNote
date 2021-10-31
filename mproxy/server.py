import logging
import typing

from aiohttp import web

from .exceptions import RequestParameterError, TemporaryUnawailableError
from .model import BaseMessage
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
            host: str,
            port: int,
            config: dict,
            debug: bool,
            retry_after: int = DEFAULT_RETRY_AFTER,
            logger: logging.Logger = None
    ) -> None:
        logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format='%(asctime)s - %(levelname)s, %(name)s: %(message)s')
        self._log_type = logger
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)
        self._log.info('Initializing application')
        self.app = web_app
        self.host = host
        self.port = port
        self.retry_after = retry_after or 0
        self._components = {'queues': queues, 'workers': workers}
        self.config = config
        self.channels = {}  # type: dict[str, VirtualChannel]
        self.app[self.MAINTENANCE_KEY] = True
        self.app.middlewares.append(self.handle_errors_middleware)
        self.app.router.add_route('GET', '/api/ping', self.ping)
        self.app.router.add_route('POST', r'/api/send/{v_channel:[\w\-]{4,24}}', self.send_message)
        self.app.router.add_route('GET', r'/api/stat/{v_channel:[\w\-]{4,24}}', self.get_channel_stat)
        for name, channel_config in self.config.items():
            self._log.debug('Registering channel %s', name)
            self.channels[name] = VirtualChannel.create_from_config(name, channel_config, self._components, logger=self._log_type)
            self.app.on_startup.append(self.channels[name].activate)
            self.app.on_shutdown.append(self.channels[name].deactivate)

    def run(self) -> None:
        self._log.debug('Starting app')
        self.app[self.MAINTENANCE_KEY] = False
        self._log.debug('Run web app at %s:%d', self.host, self.port)
        web.run_app(self.app, host=self.host, port=self.port)
        self._log.debug('App terminated')

    async def send_message(self, request: web.Request) -> web.Response:
        channel = request.match_info.get('v_channel')
        v_channel = self.channels.get(channel)
        if v_channel is None:
            self._log.error('Request to unknown channel %s', channel)
            raise RequestParameterError(f'Unknown channel {channel}')
        if not v_channel.is_running:
            self._log.error('Request in channel that is not active')
            raise TemporaryUnawailableError('Channel is not available for now')
        v_channel.add_message(BaseMessage.extract_from_request_data(await request.json()))
        return web.json_response({'status': 'success'})

    async def ping(self, request: web.Request) -> web.Response:
        return web.Response(text='OK')

    async def get_channel_stat(self, request: web.Request) -> web.Response:
        channel = request.match_info.get('v_channel')
        v_channel = self.channels.get(channel)
        if v_channel is None:
            self._log.error('Request to unknown channel %s', channel)
            raise RequestParameterError(f'Unknown channel {channel}')
        return web.json_response({'channel_stat': v_channel.get_state(), 'is_running': v_channel.is_running, 'last_error': v_channel.get_last_error()})

    @web.middleware
    async def handle_errors_middleware(self, request: web.Request, handler: typing.Callable) -> web.Response:
        try:
            if self.app[Application.MAINTENANCE_KEY]:
                return web.json_response(
                        {'status': 'error', 'error': 'Service is temporary unawailable'},
                        status=503,
                        headers={'Retry-After': str(self.retry_after)}
                )
            return await handler(request)
        except RequestParameterError as e:
            return web.json_response({'status': 'error', 'error': str(e)}, status=422)
        except TemporaryUnawailableError as e:
            return web.json_response({'status': 'error', 'error': str(e)}, status=503)
        except web.HTTPException:
            raise
        except Exception as e:
            return web.json_response({'status': 'error', 'error': str(e)}, status=500)
