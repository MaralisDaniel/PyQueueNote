import asyncio
import logging
import typing
import unittest
import unittest.mock

from aiohttp import web

import mproxy

from .stubs import Stub


class TestMProxyApplication(unittest.TestCase):
    HOST = 'http://example.com/'
    PORT = 18181
    CHANNEL_NAME = 'TestChannel'
    TEST_MESSAGE = 'This is test message'

    def setUp(self) -> None:
        self.logger_mock = unittest.mock.Mock(spec=logging.Logger)
        self.request_mock = unittest.mock.Mock(spec=web.Request)
        self.request_mock.match_info.get.return_value = TestMProxyApplication.CHANNEL_NAME
        self.request_mock.post = unittest.mock.AsyncMock(return_value={'text': TestMProxyApplication.TEST_MESSAGE})

        if self.id().split('.').pop() != 'test_delays':
            config = {
                'worker': 'Stub',
                'queue': 'AIOQueue',
                'queue_size': 3,
                'params': {
                    'min_delay': 1,
                    'max_delay': 5,
                },
            }

            with unittest.mock.patch('logging.basicConfig', autospec=True):
                self.sample = mproxy.Application(
                        web.Application(),
                        {'AIOQueue': mproxy.queues.AIOQueue},
                        {'Stub': Stub},
                        host=TestMProxyApplication.HOST,
                        port=TestMProxyApplication.PORT,
                        config={TestMProxyApplication.CHANNEL_NAME: config},
                        debug=False,
                        logger=self.logger_mock,
                )

            self.sample.app[mproxy.Application.MAINTENANCE_KEY] = False
            self.request_mock.app = self.sample.app

    def test_send_message(self):
        async def runner(handler: typing.Coroutine):
            self.sample.prepare()

            await self.sample.channels[TestMProxyApplication.CHANNEL_NAME].activate()

            return await handler

        response = asyncio.run(runner(self.sample.send_message(self.request_mock)))

        self.assertIsInstance(response, web.Response)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.text, '{"status": "success"}')

    def test_overload(self):
        async def runner(handlers: list[typing.Coroutine]):
            self.sample.prepare()

            await self.sample.channels[TestMProxyApplication.CHANNEL_NAME].activate()

            for handler in handlers:
                await handler

        payload = []

        for _ in range(0, 4):
            payload.append(self.sample.send_message(self.request_mock))

        with self.assertRaises(mproxy.TemporaryUnawailableError):
            asyncio.run(runner(payload))

    def test_delays(self):
        async def runner():
            config = {
                'worker': 'Stub',
                'queue': 'AIOQueue',
                'queue_size': 3,
                'minRetryAfter': 1,
                'maxRetryAfter': 60,
                'retryBase': 1.5,
                'params': {
                    'min_delay': 1,
                    'max_delay': 5,
                    'coin_scenario': iter([10, 15, 50]),
                    'delay_scenario': iter([1, 2, 3]),
                },
            }

            with unittest.mock.patch('logging.basicConfig', autospec=True):
                self.sample = mproxy.Application(
                        web.Application(),
                        {'AIOQueue': mproxy.queues.AIOQueue},
                        {'Stub': Stub},
                        host=TestMProxyApplication.HOST,
                        port=TestMProxyApplication.PORT,
                        config={TestMProxyApplication.CHANNEL_NAME: config},
                        debug=False,
                        logger=self.logger_mock,
                )

            self.sample.prepare()
            self.sample.app[mproxy.Application.MAINTENANCE_KEY] = False

            self.request_mock.app = self.sample.app

            await self.sample.channels[TestMProxyApplication.CHANNEL_NAME].activate()
            await self.sample.send_message(self.request_mock)

            await asyncio.sleep(13)

        asyncio.run(runner())

        message = 'Message header: "", text: "This is test message", payload is empty'
        expected = [
            f'After 1 seconds "{message}" take too long to accept by {TestMProxyApplication.CHANNEL_NAME}',
            f'After 2 seconds "{message}" take too long to accept by {TestMProxyApplication.CHANNEL_NAME}',
            f'After 3 seconds "{message}" was sent to {TestMProxyApplication.CHANNEL_NAME}',
        ]

        for search in self.logger_mock.info.call_args_list:
            if search.args[0] in expected:
                expected.remove(search.args[0])

        self.assertEqual(len(expected), 0)


if __name__ == '__main__':
    unittest.main()
