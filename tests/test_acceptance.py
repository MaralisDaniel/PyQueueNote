import asyncio
import logging
import random
import typing
import unittest
import unittest.mock
import uuid

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestServer, unittest_run_loop, unused_port

import mproxy

from .stubs import Stub


class TestMProxy(AioHTTPTestCase):
    CHANNEL_NAME = 'TestChannel'
    TEST_MESSAGE = 'My test message for Telegram'
    HOST = 'http://127.0.0.1'

    async def get_server(self, app: web.Application) -> TestServer:
        return TestServer(app, loop=self.loop, port=self.port)

    async def get_application(self) -> web.Application:
        self.port = unused_port()
        self.outer_api_data = {}  # type: dict[str, typing.Union[str, int]]

        async def stub_handler(request: web.Request) -> web.Response:
            data = await request.post()
            bot_id = request.match_info['bot_id'].replace('bot', '')

            self.outer_api_data['bot_id'] = bot_id
            self.outer_api_data['chat_id'] = int(data['chat_id'])
            self.outer_api_data['text'] = data['text']
            self.outer_api_data['method'] = request.method

            self.wait_for_api.cancel()

            return web.json_response(
                    data=self.response['data'],
                    status=self.response['code'],
            )

        self.logger = unittest.mock.Mock(spec=logging.Logger)
        self.chat_id = random.randint(100000, 1000000000)
        self.message_id = random.randint(100, 100000)

        self.bot_id = f'{random.randint(100000000, 1000000000)}:{uuid.uuid4().hex}'

        config = {
            TestMProxy.CHANNEL_NAME: {
                'worker': 'Telegram',
                'queue': 'AIOQueue',
                'queue_size': 3,
                'params': {
                    'url': f'{TestMProxy.HOST}:{self.port}/',
                    'bot_id': self.bot_id,
                    'chat_id': self.chat_id,
                    'no_notify': False,
                },
            },
        }

        self.response = {
            'code': 200,
            'data': {
                'ok': True,
                'result': {
                    'message_id': self.message_id,
                    'from': {
                        'id': self.bot_id,
                        'is_bot': True,
                        'first_name': 'TestTest',
                        'username': 'test_test',
                    },
                    'chat': {
                        'id': self.chat_id,
                        'first_name': 'Test',
                        'last_name': 'Test',
                        'username': 'test_test',
                        'type': 'private',
                    },
                    'date': random.randint(1633973467, 1634973467),
                    'text': TestMProxy.TEST_MESSAGE,
                },
            },
        }

        web_app = mproxy.Application(
                web.Application(),
                {'AIOQueue': mproxy.queues.AIOQueue},
                {'Stub': Stub, 'Telegram': mproxy.workers.Telegram},
                host=TestMProxy.HOST,
                port=self.port,
                debug=False,
                logger=self.logger,
                config=config,
        )

        web_app.app.router.add_route('*', '/{bot_id}/sendMessage', stub_handler)

        if 'maintenance' not in self.id().split('.').pop():
            web_app.app[mproxy.Application.MAINTENANCE_KEY] = False

        return web_app.app

    @unittest_run_loop
    async def test_ping(self) -> None:
        result = await self.client.request('GET', '/api/ping')

        self.assertEqual(result.status, 200)
        self.assertEqual(await result.text(), 'OK')

    @unittest_run_loop
    async def test_ping_maintenance(self) -> None:
        result = await self.client.request('GET', '/api/ping')

        self.assertEqual(result.status, 503)
        self.assertEqual(await result.text(), 'FAIL')

    @unittest_run_loop
    async def test_send_message(self) -> None:
        async def wait_for(sleep: int = 30) -> None:
            await asyncio.sleep(sleep)

            raise AssertionError('Outer API is not done correctly')

        self.wait_for_api = asyncio.create_task(wait_for())  # type: asyncio.Task

        result = await self.client.request(
                'POST', f'/api/send/{TestMProxy.CHANNEL_NAME}',
                data={'text': TestMProxy.TEST_MESSAGE},
        )

        response = await result.json()

        self.assertEqual(result.status, 200)
        self.assertEqual(response, {'status': 'success'})

        try:
            await self.wait_for_api
        except asyncio.CancelledError:
            # wait until worker complete request
            await asyncio.sleep(0.5)

        self.assertEqual(self.outer_api_data['method'], 'POST')
        self.assertEqual(self.outer_api_data['bot_id'], self.bot_id)
        self.assertEqual(self.outer_api_data['text'], TestMProxy.TEST_MESSAGE)
        self.assertEqual(self.outer_api_data['chat_id'], self.chat_id)

        self.logger.info.assert_called_with(
                'Channel %s accepted the message, its id: %d',
                'TestChannel',
                self.message_id,
        )

    @unittest_run_loop
    async def test_send_message_maintenance(self) -> None:
        result = await self.client.request(
                'POST', f'/api/send/{TestMProxy.CHANNEL_NAME}',
                data={'text': TestMProxy.TEST_MESSAGE},
        )

        response = await result.json()

        self.assertEqual(result.status, 503)
        self.assertEqual(response, {'status': 'error', 'error': 'Service is temporary unawailable'})


if __name__ == '__main__':
    unittest.main()
