import asyncio
import datetime
import logging
import random
import unittest
import unittest.mock
import uuid

from aiohttp.web import Application
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aioresponses import aioresponses
from yarl import URL

import mproxy

from tests import Stub, StubScenarioInterface


class StubScenario(StubScenarioInterface):
    def __init__(self, coin: list, delay: list):
        self.calls = {}  # type: dict[str, list]
        self._coin = coin
        self._delay = delay

        self.coins = iter(coin)
        self.delays = iter(delay)

    def __call__(self, message_id: str):
        delay = next(self.delays)
        coin = next(self.coins)

        if self.calls.get(message_id) is None:
            self.calls[message_id] = []

        self.calls[message_id].append(datetime.datetime.now())

        return delay, coin

    def reset_scenario(self):
        self.calls = {}

        self.coins = iter(self._coin)
        self.delays = iter(self._delay)


class TestMProxy(AioHTTPTestCase):
    SUCCESS_CODE = 200
    VALIDATION_ERROR_CODE = 422
    TEMPORARY_UNAWAILABLE_CODE = 503

    TEST_CHANNEL_NAME = 'TestChannel'
    STUB_CHANNEL_NAME = 'StubChannel'
    TEST_MESSAGE = 'My test message for outer API'
    HOST = 'http://example.com/'

    ACCEPTABLE_DIFF = 0.15
    ROUND_TO = 6

    async def get_application(self) -> Application:
        self.logger = unittest.mock.Mock(spec=logging.Logger)

        self.chat_id = random.randint(100000, 1000000000)
        self.bot_id = f'{random.randint(100000000, 1000000000)}:{uuid.uuid4().hex}'
        self.no_notify = False
        self.scenario_mock = StubScenario([10, 15, 50], [1, 1, 1])

        config = {
            TestMProxy.TEST_CHANNEL_NAME: {
                'worker': 'Telegram',
                'queue': 'AIOQueue',
                'queue_size': 10,
                'params': {
                    'url': TestMProxy.HOST,
                    'bot_id': self.bot_id,
                    'chat_id': self.chat_id,
                    'no_notify': self.no_notify,
                },
            },
            TestMProxy.STUB_CHANNEL_NAME: {
                'worker': 'Stub',
                'queue': 'AIOQueue',
                'queue_size': 3,
                'minRetryAfter': 0,
                'maxRetryAfter': 10,
                'retryBase': 1.5,
                'params': {
                    'min_delay': 1,
                    'max_delay': 5,
                    'scenario': self.scenario_mock,
                },
            },
        }

        self.web_app = mproxy.Application(
                Application(),
                {'AIOQueue': mproxy.queues.AIOQueue},
                {'Stub': Stub, 'Telegram': mproxy.workers.Telegram},
                host=TestMProxy.HOST,
                port=random.randint(0, 65535),
                debug=False,
                logger=self.logger,
                config=config,
        )

        if 'maintenance' not in self.id().split('.').pop():
            self.web_app.app[mproxy.Application.MAINTENANCE_KEY] = False

        return self.web_app.app

    async def setUpAsync(self) -> None:
        self.telegram_response = {
            'ok': True,
            'result': {
                'message_id': random.randint(100, 100000),
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
        }

        self.url = f'{TestMProxy.HOST}bot{self.bot_id}/sendMessage'

    @unittest_run_loop
    async def test_can_ping_in_normal_conditions(self) -> None:
        result = await self.client.request('GET', '/api/ping')

        self.assertEqual(result.status, 200)
        self.assertEqual(await result.text(), 'OK')

    @unittest_run_loop
    async def test_can_send_message_in_normal_conditions(self) -> None:
        with aioresponses(passthrough=['http://127.0.0.1']) as mock:
            mock.post(
                    self.url,
                    status=200,
                    payload=self.telegram_response,
                    headers={'Content-Type': 'application/json'},
            )

            result = await self.client.request(
                    'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                    data={'text': TestMProxy.TEST_MESSAGE},
            )

            await asyncio.sleep(0.5)

        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'status': 'success'})

        state = mock.requests.get(('POST', URL(self.url)))

        self.assertIsNotNone(state)
        self.assertDictEqual(
                state[0].kwargs,
                {
                    'data': {
                        'text': TestMProxy.TEST_MESSAGE,
                        'chat_id': self.chat_id,
                        'disable_notification': self.no_notify,
                    },
                },
        )

    @unittest_run_loop
    async def test_can_send_few_messages_in_normal_conditions(self) -> None:
        actual_calls = []
        expected_calls = []

        with aioresponses(passthrough=['http://127.0.0.1']) as mock:
            for number in range(0, 4):
                message = f'{TestMProxy.TEST_MESSAGE} - {number}'

                mock.post(
                        self.url,
                        status=200,
                        payload=self.telegram_response,
                        headers={'Content-Type': 'application/json'},
                )

                result = await self.client.request(
                        'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                        data={'text': message},
                )

                self.assertEqual(result.status, 200)
                self.assertEqual(await result.json(), {'status': 'success'})

                expected_calls.append({
                    'data': {
                        'text': message,
                        'chat_id': self.chat_id,
                        'disable_notification': self.no_notify,
                    },
                })

            await asyncio.sleep(1)

        state = mock.requests.get(('POST', URL(self.url)))

        for call in range(0, 4):
            actual_calls.append(state[call].kwargs)

        self.assertListEqual(actual_calls, expected_calls)

    @unittest_run_loop
    async def test_can_retry_to_send_message_with_delay(self) -> None:
        result = await self.client.request(
                'POST', f'/api/send/{TestMProxy.STUB_CHANNEL_NAME}',
                data={'text': TestMProxy.TEST_MESSAGE},
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'status': 'success'})

        await asyncio.sleep(7)

        state = self.web_app.channels[TestMProxy.STUB_CHANNEL_NAME].get_state()

        self.assertEqual(state['was_send'], 1)
        self.assertEqual(state['was_rejected'], 0)

        calls = [*self.scenario_mock.calls.values()][0]
        self.assertEqual(len(calls), 3)

        first_delay = calls[1] - calls[0]  # type: datetime.timedelta
        second_delay = calls[2] - calls[1]  # type: datetime.timedelta

        self.assertLess(
                round((first_delay.seconds + first_delay.microseconds / 1000000) - 2.5, TestMProxy.ROUND_TO),
                TestMProxy.ACCEPTABLE_DIFF,
        )

        self.assertLess(
                round((second_delay.seconds + second_delay.microseconds / 1000000) - 3.25, TestMProxy.ROUND_TO),
                TestMProxy.ACCEPTABLE_DIFF,
        )

    @unittest_run_loop
    async def test_can_show_channel_stat(self) -> None:
        with aioresponses(passthrough=['http://127.0.0.1']) as mock:
            for _ in range(0, 5):
                mock.post(
                        self.url,
                        status=200,
                        payload=self.telegram_response,
                        headers={'Content-Type': 'application/json'},
                )

                await self.client.request(
                        'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                        data={'text': TestMProxy.TEST_MESSAGE},
                )

        await asyncio.sleep(0.5)

        state = self.web_app.channels[TestMProxy.TEST_CHANNEL_NAME].get_state()

        self.assertEqual(state['was_send'], 5)
        self.assertEqual(state['was_rejected'], 0)

    @unittest_run_loop
    async def test_can_reject_undeliverable_message(self) -> None:
        with aioresponses(passthrough=['http://127.0.0.1']) as mock:
            mock.post(
                    self.url,
                    status=400,
                    payload={'ok': False, 'description': 'Test failure'},
                    headers={'Content-Type': 'application/json'},
            )

            result = await self.client.request(
                    'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                    data={'text': TestMProxy.TEST_MESSAGE},
            )

        await asyncio.sleep(0.5)

        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'status': 'success'})

        state = mock.requests.get(('POST', URL(self.url)))

        self.assertIsNotNone(state)
        self.assertDictEqual(
                state[0].kwargs,
                {
                    'data': {
                        'text': TestMProxy.TEST_MESSAGE,
                        'chat_id': self.chat_id,
                        'disable_notification': self.no_notify,
                    },
                },
        )

        channel_state = self.web_app.channels[TestMProxy.TEST_CHANNEL_NAME].get_state()

        self.assertEqual(channel_state['was_send'], 0)
        self.assertEqual(channel_state['was_rejected'], 1)

    @unittest_run_loop
    async def test_can_reject_empty_message(self) -> None:
        with aioresponses(passthrough=['http://127.0.0.1']) as mock:
            mock.post(
                    self.url,
                    status=200,
                    payload=self.telegram_response,
                    headers={'Content-Type': 'application/json'},
            )

            result = await self.client.request(
                    'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                    data={},
            )

        await asyncio.sleep(0.1)

        self.assertEqual(result.status, 422)
        self.assertEqual(await result.json(), {'status': 'error', 'error': 'Message could not empty'})

        self.assertDictEqual(mock.requests, {})

    @unittest_run_loop
    async def test_can_reject_send_message_in_inactive_channel(self) -> None:
        await self.web_app.channels[TestMProxy.TEST_CHANNEL_NAME].deactivate(self.web_app.app)

        with aioresponses(passthrough=['http://127.0.0.1']) as mock:
            mock.post(
                    self.url,
                    status=200,
                    payload=self.telegram_response,
                    headers={'Content-Type': 'application/json'},
            )

            result = await self.client.request(
                    'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                    data={},
            )

        await asyncio.sleep(0.1)

        self.assertEqual(result.status, 503)
        self.assertEqual(await result.json(), {'status': 'error', 'error': 'Channel is not available for now'})

        self.assertDictEqual(mock.requests, {})

    @unittest_run_loop
    async def test_can_reject_send_message_non_exists_channel(self) -> None:
        channel = 'some_channel'

        with aioresponses(passthrough=['http://127.0.0.1']) as mock:
            mock.post(
                    self.url,
                    status=200,
                    payload=self.telegram_response,
                    headers={'Content-Type': 'application/json'},
            )

            result = await self.client.request(
                    'POST', f'/api/send/{channel}',
                    data={},
            )

        await asyncio.sleep(0.1)

        self.assertEqual(result.status, TestMProxy.VALIDATION_ERROR_CODE)
        self.assertEqual(await result.json(), {'status': 'error', 'error': f'Unknown channel {channel}'})

        self.assertDictEqual(mock.requests, {})

    @unittest_run_loop
    async def test_can_reject_to_send_message_with_full_queue(self) -> None:
        for _ in range(0, 5):
            result = await self.client.request(
                    'POST', f'/api/send/{TestMProxy.STUB_CHANNEL_NAME}',
                    data={'text': TestMProxy.TEST_MESSAGE},
            )

        self.assertEqual(result.status, 503)
        self.assertEqual(
                await result.json(),
                {'status': 'error', 'error': 'Queue of this channel is full. Try again later'},
        )

    @unittest_run_loop
    async def test_can_reject_to_send_message_in_maintenance_mode(self) -> None:
        with aioresponses(passthrough=['http://127.0.0.1']) as mock:
            mock.post(
                    self.url,
                    status=200,
                    payload=self.telegram_response,
                    headers={'Content-Type': 'application/json'},
            )

            result = await self.client.request(
                    'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                    data={'text': TestMProxy.TEST_MESSAGE},
            )

        await asyncio.sleep(0.1)

        self.assertEqual(result.status, 503)
        self.assertEqual(await result.json(), {'status': 'error', 'error': 'Service is temporary unawailable'})

        self.assertDictEqual(mock.requests, {})

    @unittest_run_loop
    async def test_can_ping_in_maintenance_mode(self) -> None:
        result = await self.client.request('GET', '/api/ping')

        self.assertEqual(result.status, 503)
        self.assertEqual(await result.text(), 'FAIL')


if __name__ == '__main__':
    unittest.main()
