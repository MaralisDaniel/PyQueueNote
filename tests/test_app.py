import asyncio
import datetime
import logging
import random
from typing import Union
import unittest
import unittest.mock
import uuid
from collections import namedtuple

from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp.web import Application
from aioresponses import aioresponses
from yarl import URL

import mproxy
from tests import Stub, StubScenarioInterface

RequestCall = namedtuple('RequestCall', ['args', 'kwargs'])

HOST = 'http://example.com/'
IGNORE_HOSTS = ['http://127.0.0.1', 'http://127.0.1.1', 'http://localhost']
TEST_CHANNEL_NAME = 'TestChannel'
STUB_CHANNEL_NAME = 'StubChannel'


def get_app_config(bot_id: str, chat_id: int, scenario: StubScenarioInterface, retry_attempts: int) -> dict:
    return {
        TEST_CHANNEL_NAME: {
            'queue': {'class': 'AIOQueue', 'queue_size': 10},
            'worker': {'class': 'Telegram', 'url': HOST, 'bot_id': bot_id, 'chat_id': chat_id},
            'maxAttempts': retry_attempts,
        },
        STUB_CHANNEL_NAME: {
            'worker': {'class': 'Stub', 'min_delay': 0.5, 'max_delay': 2.5, 'scenario': scenario},
            'queue': {'class': 'AIOQueue', 'queue_size': 3},
            'minRetryAfter': 0.5,
            'maxRetryAfter': 10,
            'retryBase': 1.5,
        },
    }


class StubScenario(StubScenarioInterface):
    def __init__(self, coin: list, delay: list):
        self.calls = {}  # type: dict[uuid.UUID, list]
        self._coin = coin
        self._delay = delay
        self.coins = iter(coin)
        self.delays = iter(delay)

    def __call__(self, message_id: uuid.UUID):
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
    MESSAGE = 'My test message for outer API'
    ROUND_TO = 0
    FEW_MESSAGES_COUNT = 5
    RETRY_ATTEMPTS = 2

    async def get_application(self) -> Application:
        self.logger = unittest.mock.Mock(spec=logging.Logger)
        self.chat_id = random.randint(100000, 1000000000)
        self.bot_id = f'{random.randint(100000000, 1000000000)}:{uuid.uuid4().hex}'
        self.no_notify = False
        self.scenario_mock = StubScenario([10, 15, 50], [0.5, 0.5, 0.5])
        self.web_app = mproxy.Application(
                Application(),
                {'AIOQueue': mproxy.queues.AIOQueue},
                {'Stub': Stub, 'Telegram': mproxy.workers.Telegram},
                host=HOST,
                port=random.randint(0, 65535),
                debug=False,
                logger=self.logger,
                config=get_app_config(self.bot_id, self.chat_id, self.scenario_mock, self.RETRY_ATTEMPTS),
        )
        if 'maintenance' not in self.id().split('.').pop():
            self.web_app.app[mproxy.Application.MAINTENANCE_KEY] = False
        return self.web_app.app

    async def setUpAsync(self) -> None:
        self.telegram_response = {
            'ok': True,
            'result': {
                'message_id': random.randint(100, 100000),
                'from': {'id': self.bot_id, 'is_bot': True, 'first_name': 'TestTest', 'username': 'test_test'},
                'chat': {'id': self.chat_id, 'first_name': 'Test', 'last_name': 'Test', 'username': 'test_test', 'type': 'private'},
                'date': random.randint(1633973467, 1634973467),
                'text': self.MESSAGE,
            },
        }
        self.url = f'{HOST}bot{self.bot_id}/sendMessage'

    @unittest_run_loop
    async def test_can_ping_in_normal_conditions(self) -> None:
        result = await self.client.request('GET', '/api/ping')
        self.assertEqual(result.status, 200)
        self.assertEqual(await result.text(), 'OK')

    @unittest_run_loop
    async def test_can_send_message_in_normal_conditions(self) -> None:
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            mock.post(self.url, status=200, payload=self.telegram_response, headers={'Content-Type': 'application/json'})
            result = await self.client.request(
                    'POST',
                    f'/api/send/{TEST_CHANNEL_NAME}',
                    json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
            )
            await asyncio.sleep(0.15)
        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'status': 'success'})
        self.check_request_count(mock.requests)
        self.check_request_calls(
                mock.requests,
                {'data': {'text': self.MESSAGE, 'chat_id': self.chat_id, 'disable_notification': self.no_notify}},
                url_key=('POST', URL(self.url)),
        )

    @unittest_run_loop
    async def test_can_send_few_messages_in_normal_conditions(self) -> None:
        expected_calls = []
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            for number in range(0, self.FEW_MESSAGES_COUNT):
                message = f'{self.MESSAGE} - {number}'
                mock.post(self.url, status=200, payload=self.telegram_response, headers={'Content-Type': 'application/json'})
                result = await self.client.request(
                        'POST',
                        f'/api/send/{TEST_CHANNEL_NAME}',
                        json={'message': f'{self.MESSAGE} - {number}', 'params': {'disable_notification': self.no_notify}},
                )
                self.assertEqual(result.status, 200)
                self.assertEqual(await result.json(), {'status': 'success'})
                expected_calls.append({'data': {'text': message, 'chat_id': self.chat_id, 'disable_notification': self.no_notify}})
            await asyncio.sleep(0.5)
        self.check_request_count(mock.requests, request_per_url_count=self.FEW_MESSAGES_COUNT)
        for call in range(0, self.FEW_MESSAGES_COUNT):
            self.check_request_calls(mock.requests, expected_calls[call], url_key=('POST', URL(self.url)), call_key=call)

    @unittest_run_loop
    async def test_can_retry_to_send_message_with_delay(self) -> None:
        delay = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(0, 1)).strftime('%a, %d %b %Y %H:%M:%S %Z')
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            mock.post(self.url, status=502, headers={'Content-Type': 'text/plain', 'Retry-After': delay})
            result = await self.client.request(
                    'POST',
                    f'/api/send/{TEST_CHANNEL_NAME}',
                    json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
            )
            await asyncio.sleep(0.5)
            mock.post(self.url, status=200, payload=self.telegram_response, headers={'Content-Type': 'application/json'})
            await asyncio.sleep(1.75)
        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'status': 'success'})
        self.check_request_count(mock.requests, request_per_url_count=2)
        req = {'data': {'text': self.MESSAGE, 'chat_id': self.chat_id, 'disable_notification': self.no_notify}}
        self.check_request_calls(mock.requests, req, url_key=('POST', URL(self.url)), call_key=0)
        self.check_request_calls(mock.requests, req, url_key=('POST', URL(self.url)), call_key=1)

    @unittest_run_loop
    async def test_can_reject_send_message_after_numbers_of_attempts(self) -> None:
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            for _ in range(0, self.RETRY_ATTEMPTS):
                mock.post(self.url, status=502, headers={'Content-Type': 'text/plain', 'Retry-After': '0'})
            result = await self.client.request(
                    'POST',
                    f'/api/send/{TEST_CHANNEL_NAME}',
                    json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
            )
            await asyncio.sleep(0.75)
        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'status': 'success'})
        self.check_request_count(mock.requests, request_per_url_count=2)
        req = {'data': {'text': self.MESSAGE, 'chat_id': self.chat_id, 'disable_notification': self.no_notify}}
        self.check_request_calls(mock.requests, req, url_key=('POST', URL(self.url)), call_key=0)
        self.check_request_calls(mock.requests, req, url_key=('POST', URL(self.url)), call_key=1)

    @unittest_run_loop
    async def test_can_retry_with_exponential_delay(self) -> None:
        result = await self.client.request(
                'POST',
                f'/api/send/{STUB_CHANNEL_NAME}',
                json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
        )
        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'status': 'success'})
        await asyncio.sleep(6.75)
        state = self.web_app.channels[STUB_CHANNEL_NAME].get_state()
        self.assertEqual(state['was_send'], 1)
        self.assertEqual(state['was_rejected'], 0)
        calls = [*self.scenario_mock.calls.values()][0]
        self.assertEqual(len(calls), 3)
        first_delay = calls[1] - calls[0]  # type: datetime.timedelta
        second_delay = calls[2] - calls[1]  # type: datetime.timedelta
        self.assertAlmostEqual((first_delay.seconds + first_delay.microseconds / 1000000), 2.5, self.ROUND_TO)
        self.assertAlmostEqual((second_delay.seconds + second_delay.microseconds / 1000000), 3.25, self.ROUND_TO)

    @unittest_run_loop
    async def test_can_show_channel_stat(self) -> None:
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            for _ in range(0, self.FEW_MESSAGES_COUNT):
                mock.post(self.url, status=200, payload=self.telegram_response, headers={'Content-Type': 'application/json'})
                await self.client.request(
                        'POST',
                        f'/api/send/{TEST_CHANNEL_NAME}',
                        json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
                )
        await asyncio.sleep(0.15)
        state = await self.client.request('GET', f'/api/stat/{TEST_CHANNEL_NAME}')
        self.assertDictEqual(
                await state.json(),
                {'channel_stat': {'was_send': self.FEW_MESSAGES_COUNT, 'was_rejected': 0, 'in_queue': 0}, 'is_running': True, 'last_error': None},
        )

    @unittest_run_loop
    async def test_can_handle_undeliverable_message(self) -> None:
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            mock.post(self.url, status=400, payload={'ok': False, 'description': 'Test failure'}, headers={'Content-Type': 'application/json'})
            result = await self.client.request(
                    'POST',
                    f'/api/send/{TEST_CHANNEL_NAME}',
                    json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
            )
        await asyncio.sleep(0.15)
        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'status': 'success'})
        self.check_request_count(mock.requests)
        self.check_request_calls(
                mock.requests,
                {'data': {'text': self.MESSAGE, 'chat_id': self.chat_id, 'disable_notification': self.no_notify}},
                url_key=('POST', URL(self.url)),
        )
        channel_state = self.web_app.channels[TEST_CHANNEL_NAME].get_state()
        self.assertEqual(channel_state['was_send'], 0)
        self.assertEqual(channel_state['was_rejected'], 1)

    @unittest_run_loop
    async def test_can_handle_unreachable_url(self) -> None:
        with aioresponses(passthrough=IGNORE_HOSTS) as m:
            m.post(self.url, status=404)
            result = await self.client.request(
                    'POST',
                    f'/api/send/{TEST_CHANNEL_NAME}',
                    json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
            )
        await asyncio.sleep(0.15)
        self.assertEqual(result.status, 200)
        self.assertEqual(await result.json(), {'status': 'success'})
        self.check_request_count(m.requests)
        self.check_request_calls(
                m.requests,
                {'data': {'text': self.MESSAGE, 'chat_id': self.chat_id, 'disable_notification': self.no_notify}},
                url_key=('POST', URL(self.url)),
        )
        channel_state = self.web_app.channels[TEST_CHANNEL_NAME].get_state()
        self.assertEqual(channel_state['was_send'], 0)
        self.assertEqual(channel_state['was_rejected'], 1)

    @unittest_run_loop
    async def test_can_reject_empty_message(self) -> None:
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            mock.post(self.url, status=200, payload=self.telegram_response, headers={'Content-Type': 'application/json'})
            result = await self.client.request('POST', f'/api/send/{TEST_CHANNEL_NAME}', json={})
        await asyncio.sleep(0.1)
        self.assertEqual(result.status, 422)
        self.assertEqual(await result.json(), {'status': 'error', 'error': 'Message could not empty'})
        self.assertDictEqual(mock.requests, {})

    @unittest_run_loop
    async def test_can_reject_send_message_in_inactive_channel(self) -> None:
        await self.web_app.channels[TEST_CHANNEL_NAME].deactivate(self.web_app.app)
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            mock.post(self.url, status=200, payload=self.telegram_response, headers={'Content-Type': 'application/json'})
            result = await self.client.request(
                    'POST',
                    f'/api/send/{TEST_CHANNEL_NAME}',
                    json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
            )
        await asyncio.sleep(0.1)
        self.assertEqual(result.status, 503)
        self.assertEqual(await result.json(), {'status': 'error', 'error': 'Channel is not available for now'})
        self.assertDictEqual(mock.requests, {})

    @unittest_run_loop
    async def test_can_reject_send_message_non_exists_channel(self) -> None:
        channel = 'some_channel'
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            mock.post(self.url, status=200, payload=self.telegram_response, headers={'Content-Type': 'application/json'})
            result = await self.client.request(
                    'POST',
                    f'/api/send/{channel}',
                    json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
            )
        await asyncio.sleep(0.1)
        self.assertEqual(result.status, self.VALIDATION_ERROR_CODE)
        self.assertEqual(await result.json(), {'status': 'error', 'error': f'Unknown channel {channel}'})
        self.assertDictEqual(mock.requests, {})

    @unittest_run_loop
    async def test_can_reject_to_send_message_with_full_queue(self) -> None:
        for _ in range(0, self.FEW_MESSAGES_COUNT):
            result = await self.client.request('POST', f'/api/send/{STUB_CHANNEL_NAME}', json={'message': self.MESSAGE})
        self.assertEqual(result.status, 503)
        self.assertEqual(await result.json(), {'status': 'error', 'error': 'Queue of this channel is full. Try again later'})

    @unittest_run_loop
    async def test_can_reject_show_channel_stat_of_non_exists_channel(self) -> None:
        channel = 'some_channel'
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            mock.post(self.url, status=200, payload=self.telegram_response, headers={'Content-Type': 'application/json'})
            result = await self.client.request('GET', f'/api/stat/{channel}')
        await asyncio.sleep(0.1)
        self.assertEqual(result.status, self.VALIDATION_ERROR_CODE)
        self.assertEqual(await result.json(), {'status': 'error', 'error': f'Unknown channel {channel}'})
        self.assertDictEqual(mock.requests, {})

    @unittest_run_loop
    async def test_can_reject_to_send_message_in_maintenance_mode(self) -> None:
        with aioresponses(passthrough=IGNORE_HOSTS) as mock:
            mock.post(self.url, status=200, payload=self.telegram_response, headers={'Content-Type': 'application/json'})
            result = await self.client.request(
                    'POST',
                    f'/api/send/{TEST_CHANNEL_NAME}',
                    json={'message': self.MESSAGE, 'params': {'disable_notification': self.no_notify}},
            )
        await asyncio.sleep(0.1)
        self.assertEqual(result.status, 503)
        self.assertEqual(await result.json(), {'status': 'error', 'error': 'Service is temporary unawailable'})
        self.assertDictEqual(mock.requests, {})

    @unittest_run_loop
    async def test_can_reject_to_show_channel_stat_in_maintenance_mode(self) -> None:
        result = await self.client.request('GET', f'/api/stat/{TEST_CHANNEL_NAME}')
        self.assertEqual(result.status, 503)
        self.assertEqual(await result.json(), {'status': 'error', 'error': 'Service is temporary unawailable'})

    @unittest_run_loop
    async def test_can_ping_in_maintenance_mode(self) -> None:
        result = await self.client.request('GET', '/api/ping')
        self.assertEqual(result.status, 503)
        self.assertEqual(await result.text(), 'FAIL')

    def check_request_count(self, requests: dict, unique_url_count: int = 1, request_per_url_count: int = 1) -> None:
        self.assertEqual(len(requests), unique_url_count)
        for request_per_url in requests.values():
            self.assertEqual(len(request_per_url), request_per_url_count)

    def check_request_calls(self, requests: dict, data: dict, url_key: tuple = None, call_key: int = 0) -> None:
        request_calls = requests.get(url_key) if url_key else next(iter(requests.values()), None)  # type: Union[None, list[RequestCall]]
        self.assertIsNotNone(request_calls)
        self.assertDictEqual(request_calls[call_key].kwargs, data)


if __name__ == '__main__':
    unittest.main()
