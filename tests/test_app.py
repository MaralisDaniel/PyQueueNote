import asyncio
import logging
import random
import unittest
import unittest.mock
import uuid

from aiohttp.web import Application
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aioresponses import aioresponses

import mproxy

from tests import Stub


class TestMProxy(AioHTTPTestCase):
    SUCCESS_CODE = 200
    VALIDATION_ERROR_CODE = 422
    TEMPORARY_UNAWAILABLE_CODE = 503

    TEST_CHANNEL_NAME = 'TestChannel'
    STUB_CHANNEL_NAME = 'StubChannel'
    TEST_MESSAGE = 'My test message for outer API'
    HOST = 'http://example.com/'

    async def get_application(self) -> Application:
        self.logger = unittest.mock.Mock(spec=logging.Logger)

        self.chat_id = random.randint(100000, 1000000000)
        self.bot_id = f'{random.randint(100000000, 1000000000)}:{uuid.uuid4().hex}'

        config = {
            TestMProxy.TEST_CHANNEL_NAME: {
                'worker': 'Telegram',
                'queue': 'AIOQueue',
                'queue_size': 10,
                'params': {
                    'url': TestMProxy.HOST,
                    'bot_id': self.bot_id,
                    'chat_id': self.chat_id,
                    'no_notify': False,
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
                    'coin_scenario': iter([10, 15, 50]),
                    'delay_scenario': iter([1, 1, 1]),
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

    @unittest_run_loop
    async def test_can_ping_in_normal_conditions(self) -> None:
        result = await self.client.request('GET', '/api/ping')

        self.assertEqual(result.status, 200)
        self.assertEqual(await result.text(), 'OK')

    @unittest_run_loop
    async def test_can_send_message_in_normal_conditions(self) -> None:
        message_id = random.randint(100, 100000)

        telegram_response = {
            'ok': True,
            'result': {
                'message_id': message_id,
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

        with aioresponses(passthrough=['http://127.0.0.1']) as m:
            url = f'{TestMProxy.HOST}bot{self.bot_id}/sendMessage'
            m.post(url, status=200, payload=telegram_response, headers={'Content-Type': 'application/json'})

            result = await self.client.request(
                    'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                    data={'text': TestMProxy.TEST_MESSAGE},
            )

            response = await result.json()

            await asyncio.sleep(0.5)

        self.assertEqual(result.status, 200)
        self.assertEqual(response, {'status': 'success'})

        channel_stat = self.web_app.channels[TestMProxy.TEST_CHANNEL_NAME].get_state()

        self.assertEqual(channel_stat['was_send'], 1)
        self.assertEqual(channel_stat['was_rejected'], 0)
        self.assertIsNone(channel_stat['current_task'])

    @unittest_run_loop
    async def test_can_send_few_messages_in_normal_conditions(self) -> None:
        message_id = random.randint(100, 100000)

        telegram_response = {
            'ok': True,
            'result': {
                'message_id': message_id,
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

        with aioresponses(passthrough=['http://127.0.0.1']) as m:
            url = f'{TestMProxy.HOST}bot{self.bot_id}/sendMessage'

            for _ in range(0, 4):
                m.post(url, status=200, payload=telegram_response, headers={'Content-Type': 'application/json'})

                result = await self.client.request(
                        'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                        data={'text': TestMProxy.TEST_MESSAGE},
                )

                response = await result.json()

                self.assertEqual(result.status, 200)
                self.assertEqual(response, {'status': 'success'})

            await asyncio.sleep(1)

            channel_stat = self.web_app.channels[TestMProxy.TEST_CHANNEL_NAME].get_state()

        self.assertEqual(channel_stat['was_send'], 4)
        self.assertEqual(channel_stat['was_rejected'], 0)
        self.assertIsNone(channel_stat['current_task'])

    @unittest_run_loop
    async def test_can_retry_to_send_message(self) -> None:
        result = await self.client.request(
                'POST', f'/api/send/{TestMProxy.STUB_CHANNEL_NAME}',
                data={'text': TestMProxy.TEST_MESSAGE},
        )

        response = await result.json()

        self.assertEqual(result.status, 200)
        self.assertEqual(response, {'status': 'success'})

        await asyncio.sleep(0.5)

        state = self.web_app.channels[TestMProxy.STUB_CHANNEL_NAME].get_state()

        self.assertEqual(state['was_send'], 0)
        self.assertEqual(state['was_rejected'], 0)
        self.assertIsNotNone(state['current_task'])

        task_id = state['current_task']

        await asyncio.sleep(5)

        state = self.web_app.channels[TestMProxy.STUB_CHANNEL_NAME].get_state()

        self.assertEqual(state['was_send'], 0)
        self.assertEqual(state['was_rejected'], 0)
        self.assertEqual(state['current_task'], task_id)

        await asyncio.sleep(2)

        state = self.web_app.channels[TestMProxy.STUB_CHANNEL_NAME].get_state()

        self.assertEqual(state['was_send'], 1)
        self.assertEqual(state['was_rejected'], 0)
        self.assertIsNone(state['current_task'])

    @unittest_run_loop
    async def test_can_reject_empty_message(self) -> None:
        result = await self.client.request(
                'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                data={},
        )

        response = await result.json()

        self.assertEqual(result.status, 422)
        self.assertEqual(response, {'status': 'error', 'error': 'Message could not empty'})

        channel_stat = self.web_app.channels[TestMProxy.TEST_CHANNEL_NAME].get_state()

        self.assertEqual(channel_stat['was_send'], 0)
        self.assertEqual(channel_stat['was_rejected'], 0)
        self.assertIsNone(channel_stat['current_task'])

    @unittest_run_loop
    async def test_can_reject_send_message_in_inactive_channel(self) -> None:
        await self.web_app.channels[TestMProxy.TEST_CHANNEL_NAME].deactivate(self.web_app.app)

        result = await self.client.request(
                'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                data={},
        )

        response = await result.json()

        self.assertEqual(result.status, 503)
        self.assertEqual(response, {'status': 'error', 'error': 'Channel is not available for now'})

    @unittest_run_loop
    async def test_can_reject_send_message_non_exists_channel(self) -> None:
        channel = 'some_channel'

        result = await self.client.request(
                'POST', f'/api/send/{channel}',
                data={},
        )

        response = await result.json()

        self.assertEqual(result.status, TestMProxy.VALIDATION_ERROR_CODE)
        self.assertEqual(response, {'status': 'error', 'error': f'Unknown channel {channel}'})

    @unittest_run_loop
    async def test_can_reject_to_send_message_with_full_queue(self) -> None:
        for _ in range(0, 5):
            result = await self.client.request(
                    'POST', f'/api/send/{TestMProxy.STUB_CHANNEL_NAME}',
                    data={'text': TestMProxy.TEST_MESSAGE},
            )

        response = await result.json()

        self.assertEqual(result.status, 503)
        self.assertEqual(response, {'status': 'error', 'error': 'Queue of this channel is full. Try again later'})

    @unittest_run_loop
    async def test_can_reject_to_send_message_in_maintenance_mode(self) -> None:
        result = await self.client.request(
                'POST', f'/api/send/{TestMProxy.TEST_CHANNEL_NAME}',
                data={'text': TestMProxy.TEST_MESSAGE},
        )

        response = await result.json()

        self.assertEqual(result.status, 503)
        self.assertEqual(response, {'status': 'error', 'error': 'Service is temporary unawailable'})

    @unittest_run_loop
    async def test_can_ping_in_maintenance_mode(self) -> None:
        result = await self.client.request('GET', '/api/ping')

        self.assertEqual(result.status, 503)
        self.assertEqual(await result.text(), 'FAIL')


if __name__ == '__main__':
    unittest.main()
