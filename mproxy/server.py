from __future__ import annotations

import argparse
import logging

from aiohttp import web
from .exceptions import *
import mproxy.vchannel


DEFAULT_RETRY_AFTER = 120
MAINTENANCE_KEY = 'maintenance'
DEFAULT_LOGGER_NAME = 'm-proxy.server'


# Low-level api - classes for organizing the application


class Server:
    def __init__(
            self, web_app: web.Application,
            *,
            host: str,
            port: int,
            logger: logging.Logger = None
    ) -> None:
        self.app = web_app
        self.host = host
        self.port = port
        self.idle = True
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

        self.app[MAINTENANCE_KEY] = True

    def run(self) -> None:
        self.idle = False
        self.app[MAINTENANCE_KEY] = False
        self._log.debug('Run web app at %s:%d', self.host, self.port)

        web.run_app(self.app, host=self.host, port=self.port)

    def set_routing(self, route: str, method: str, handler: callable) -> None:
        if not self.idle:
            raise ServerIsRunningError('Unable to register new route on running web server')

        self._log.debug('Register handler %s on %s %s', handler.__name__, method, route)

        self.app.router.add_route(method, route, handler)

    def set_middleware(self, middleware: callable) -> None:
        if not self.idle:
            raise ServerIsRunningError('Unable to set middleware on running web server')

        self._log.debug('Register middleware %s', middleware.__name__)

        self.app.middlewares.append(middleware)

    def set_initial_task(self, task: callable) -> None:
        if not self.idle:
            raise ServerIsRunningError('Unable to set task on running web server')

        self._log.debug('Set task %s on startup', task.__name__)

        self.app.on_startup.append(task)

    def set_finishing_task(self, task: callable) -> None:
        if not self.idle:
            raise ServerIsRunningError('Unable to set task on running web server')

        self._log.debug('Set task %s on shutdown', task.__name__)

        self.app.on_shutdown.append(task)


class HTTPParameter:
    def __init__(self, name: str, value: any, param_type: str) -> None:
        self._value = value
        self.name = name
        self._type = param_type

    @property
    def value(self):
        return self._value

    @classmethod
    async def extract_param(
            cls,
            name: str,
            request: web.Request,
            *,
            required: bool = True,
            default: any = None,
    ) -> HTTPParameter:
        param = request.match_info.get(name)

        if param is not None:
            return cls(name, param, 'resource')

        param = (await request.post()).get(name)

        if param is not None:
            return cls(name, param, 'POST')

        param = request.query.get(name)

        if param is not None:
            return cls(name, param, 'GET')

        if required:
            raise RequestParameterError(f'Request parameter {name} is not presented in the request')

        return cls(name, default, 'default')

    def __repr__(self) -> str:
        return f'Parameter {self.name}: {self._value} extracted from {self._type}'


class Controller:
    def __init__(
            self,
            vc_collection: mproxy.vchannel.VCCollection,
            *,
            retry_after: int = DEFAULT_RETRY_AFTER,
            logger: logging.Logger = None
    ) -> None:
        self.retry_after = retry_after
        self.vc_collection = vc_collection
        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

    async def send_message(self, request: web.Request) -> web.Response:
        channel = await HTTPParameter.extract_param('v_channel', request)
        self._log.debug('Request parameter %s is read', channel)

        delay = await HTTPParameter.extract_param('delay', request, required=False, default=0)
        self._log.debug('Request parameter %s is read', delay)

        message = await HTTPParameter.extract_param('message', request)
        self._log.debug('Request parameter %s is read', message)

        if not self.vc_collection.is_channel(channel.value):
            self._log.warning('Request to unknown channel %s', channel.value)

            raise RequestParameterError(f'Unknown channel {channel.value}')

        if len(message.value) == 0:
            self._log.warning('Empty message was passed')

            raise RequestParameterError(f'Message could not be empty')

        v_channel = self.vc_collection.get_channel(channel.value)

        if not v_channel.is_running:
            self._log.warning('Request in channel that is not active')

            raise TemporaryUnawailableError(f'Channel is not available for now')

        v_channel.get_queue().add_task(message.value)

        self._log.debug('Request completed')

        return web.json_response({'status': True})

    async def ping(self, request: web.Request) -> web.Response:
        if request.app[MAINTENANCE_KEY]:
            return web.Response(status=503, text='FAIL', headers={'Retry-After': str(self.retry_after)})

        return web.Response(text='OK')


@web.middleware
async def handle_errors_middleware(request: web.Request, handler: callable) -> web.Response:
    try:
        return await handler(request)
    except RequestParameterError as e:
        return web.json_response({'success': False, 'error': str(e)}, status=422)
    except TemporaryUnawailableError as e:
        return web.json_response({'success': False, 'error': str(e)}, status=503)
    except web.HTTPException:
        raise
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)}, status=500)


# High-level api - classes to serve the application like init`n`forget


class CLIRunner(argparse.ArgumentParser):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.add_argument(
                '--host',
                '-H',
                help='Host name or IP address to listen',
                default='localhost',
                metavar='Host',
                dest='host',
        )

        self.add_argument(
                '--port',
                '-P',
                type=int,
                help='Port to listen',
                default=8080,
                metavar='Port',
                dest='port',
        )

        self.add_argument(
                '--config',
                '-c',
                help='virtual channel\'s config filename',
                default='config.example.yaml',
                metavar='config filename',
                dest='config',
        )

        self.add_argument(
                '--debug',
                '-d',
                help='Enable debug mode or not',
                action='store_true',
                dest='debug',
        )

    def error(self, message: str) -> None:
        self._print_message(f'{self.prog} - error: {message}')
        self.print_help()
        self.exit(2)


class Application:
    def __init__(
            self,
            *,
            host: str,
            port: int,
            config_filename: str,
            debug: bool,
            logger: logging.Logger = None
    ) -> None:
        self.inited = False

        logging.basicConfig(
                level=logging.DEBUG if debug else logging.INFO,
                format='%(asctime)s - %(levelname)s, %(name)s: %(message)s'
        )

        self._log = logger or logging.getLogger(DEFAULT_LOGGER_NAME)

        self._log.info('Initializing components')

        self.server = Server(web.Application(), host=host, port=port, logger=logger)
        self.config = mproxy.ConfigReader(config_filename)
        self.vc_collection = mproxy.VCCollection(self.config)
        self.controller = Controller(self.vc_collection, logger=logger)

    def init(self) -> None:
        self._log.debug('Reading virtual channels configuration')

        self.config.read()
        self.vc_collection.load_channels()

        self._log.debug('Setting routing and middlewares')

        self.server.set_middleware(handle_errors_middleware)
        self.server.set_routing('/api/ping', 'GET', self.controller.ping)
        self.server.set_routing(r'/api/send/{v_channel:[\w\-]{4,24}}', 'POST', self.controller.send_message)

        self._log.debug('Setting startup and shutdown events')

        for channel in self.vc_collection.channels.values():
            self.server.set_initial_task(channel.activate)
            self.server.set_finishing_task(channel.deactivate)

        self._log.info('Application is ready to operate')

        self.inited = True

    def run(self) -> None:
        self._log.debug('Starting app')

        if not self.inited:
            raise RuntimeError('Application is not inited')

        self.server.run()

        self._log.debug('App terminated')


__all__ = ['Application', 'Server', 'Controller', 'CLIRunner', 'handle_errors_middleware']
