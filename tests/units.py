import asyncio
import datetime
import logging
import random
import uuid
import unittest
import unittest.mock
from aiohttp.web import Request, Response, Application, HTTPException

import mproxy
from stubs import Stub


class TestWorkerAwaitError(unittest.TestCase):
    STATE = 503
    MESSAGE = 'Test error message'
    DELAY = 30

    def test_get_delay_in_seconds(self) -> None:
        data_provider = {
            'as int': TestWorkerAwaitError.DELAY,
            'as float': float(TestWorkerAwaitError.DELAY),
            'as str': str(TestWorkerAwaitError.DELAY),
            'as UTC date': (
                    datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(0, TestWorkerAwaitError.DELAY)
            ).strftime('%a, %d %b %Y %H:%M:%S %Z'),
            'as TZ date': (
                    datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(0, TestWorkerAwaitError.DELAY)
            ).strftime('%a, %d %b %Y %H:%M:%S %z'),
            'as GMT date': (
                    datetime.datetime.now() + datetime.timedelta(0, TestWorkerAwaitError.DELAY)
            ).strftime('%a, %d %b %Y %H:%M:%S GMT'),
        }

        for name, data_set in data_provider.items():
            with self.subTest(f'Test get delay in seconds with data set "{name}"'):
                sample = mproxy.WorkerAwaitError(
                        TestWorkerAwaitError.DELAY,
                        TestWorkerAwaitError.MESSAGE,
                        delay=data_set,
                )

                self.assertEqual(TestWorkerAwaitError.DELAY, sample.get_delay_in_seconds())


class TestMessage(unittest.TestCase):
    def test_repr(self) -> None:
        data_provider = {
            'Full': {
                'data': {'text': 'Test message', 'header': 'Message header', 'payload': [b'123456', b'123456']},
                'expected': 'Message header: "Message header", text: "Test message", payload is not empty',
            },
            'Without payload': {
                'data': {'text': 'Test message', 'header': 'Message header'},
                'expected': 'Message header: "Message header", text: "Test message", payload is empty',
            },
            'Without header': {
                'data': {'text': 'Test message', 'payload': [b'123456', b'123456']},
                'expected': 'Message header: "", text: "Test message", payload is not empty',
            },
            'Without text': {
                'data': {'header': 'Message header', 'payload': [b'123456', b'123456']},
                'expected': 'Message header: "Message header", text: "", payload is not empty',
            },
        }

        for name, data_set in data_provider.items():
            with self.subTest(msg=f'Test Message repr with dataset "{name}"'):
                sample = mproxy.Message(**data_set['data'])

                self.assertEqual(repr(sample), data_set['expected'])

    def test_static_create(self) -> None:
        data_provider = {
            'Full': {
                'data': {'text': 'Test message', 'header': 'Message header', 'payload': [b'123456', b'123456']},
                'expected': {'text': 'Test message', 'header': 'Message header', 'payload': [b'123456', b'123456']},
            },
            'Without payload': {
                'data': {'text': 'Test message', 'header': 'Message header'},
                'expected': {'text': 'Test message', 'header': 'Message header', 'payload': None},
            },
            'Without header': {
                'data': {'text': 'Test message', 'payload': [b'123456', b'123456']},
                'expected': {'text': 'Test message', 'header': None, 'payload': [b'123456', b'123456']},
            },
            'Without text': {
                'data': {'header': 'Message header', 'payload': [b'123456', b'123456']},
                'expected': {'text': None, 'header': 'Message header', 'payload': [b'123456', b'123456']},
            },
            'Defaults only': {
                'data': {},
                'default': {'text': 'Test message', 'header': 'Message header', 'payload': [b'123456', b'123456']},
                'expected': {'text': 'Test message', 'header': 'Message header', 'payload': [b'123456', b'123456']},
            },
            'Data and defaults': {
                'data': {'text': 'Test message', 'header': 'Message header', 'payload': [b'123456', b'123456']},
                'default': {'text': 'Override message', 'header': 'Override header', 'payload': [b'987654']},
                'expected': {'text': 'Test message', 'header': 'Message header', 'payload': [b'123456', b'123456']},
            },
            'Empty': {
                'data': {},
                'required': False,
                'expected': {'text': None, 'header': None, 'payload': None},
            },
        }

        for name, data_set in data_provider.items():
            with self.subTest(msg=f'Test Message static constructor with data set "{name}"'):
                sample = mproxy.Message.extract_from_request_data(
                        data_set['data'],
                        default=data_set.get('default', {}),
                        required=data_set.get('required', True),
                )

                for field, value in data_set['expected'].items():
                    self.assertEqual(getattr(sample, field), value)

    def test_static_empty(self) -> None:
        with self.assertRaises(mproxy.RequestParameterError):
            mproxy.Message.extract_from_request_data({}, required=True)


class TestAIOQueue(unittest.TestCase):
    DELAY = 5

    def setUp(self) -> None:
        self.mock_logger = unittest.mock.Mock(spec=logging.Logger)
        self.mock_message = unittest.mock.Mock(spec=mproxy.Message)

    def test_create(self) -> None:
        with unittest.mock.patch('asyncio.Queue') as mock:
            mproxy.AIOQueue(2, self.mock_logger)

        mock.assert_called_once_with(maxsize=2)

    def test_put(self) -> None:
        with unittest.mock.patch('asyncio.Queue', autospec=True) as mock:
            sample = mproxy.AIOQueue(2, self.mock_logger)

            sample.add_task(self.mock_message, TestAIOQueue.DELAY)

        mock.return_value.put_nowait.assert_called_once_with(self.mock_message)

        self.mock_logger.debug.assert_called()

    def test_get(self) -> None:
        with unittest.mock.patch('asyncio.Queue', autospec=True) as mock:
            sample = mproxy.AIOQueue(5, self.mock_logger)

            asyncio.run(sample.get_task())

        mock.return_value.task_done.assert_called_once()
        mock.return_value.get.assert_awaited_once()

        self.mock_logger.debug.assert_called()

    def test_amount_of_items(self) -> None:
        with unittest.mock.patch('asyncio.Queue', autospec=True) as mock:
            sample = mproxy.AIOQueue(2, self.mock_logger)

            sample.current_items_count()

        mock.return_value.qsize.assert_called_once()

    def test_overflow(self) -> None:
        with unittest.mock.patch('asyncio.Queue', autospec=True) as mock:
            mock.return_value.put_nowait.side_effect = ['test', asyncio.QueueFull]

            sample = mproxy.AIOQueue(1, self.mock_logger)

            sample.add_task(self.mock_message, TestAIOQueue.DELAY)

            with self.assertRaises(mproxy.TemporaryUnawailableError):
                sample.add_task(self.mock_message, TestAIOQueue.DELAY)

        self.assertEqual(mock.return_value.put_nowait.call_count, 2)

        self.mock_logger.debug.assert_called()
        self.mock_logger.warning.assert_called_once()


class TestStubWorker(unittest.TestCase):
    TEST_MESSAGE = 'Test Message 1'
    CHANNEL_NAME = 'TestChannel'

    def setUp(self) -> None:
        self.mock_logger = unittest.mock.Mock(spec=logging.Logger)
        self.mock_message = unittest.mock.Mock(spec=mproxy.Message, text=TestStubWorker.TEST_MESSAGE)

    def test_operate_success(self) -> None:
        min_delay = 2
        max_delay = 10
        coin_error = 10
        coin_delay = 30

        with unittest.mock.patch('random.randint', autospec=True) as mock_random:
            with unittest.mock.patch('asyncio.sleep', autospec=True) as mock_sleep:
                mock_random.side_effect = [5, 50]

                sample = Stub(
                        TestStubWorker.CHANNEL_NAME,
                        logger=self.mock_logger,
                        min_delay=min_delay,
                        max_delay=max_delay,
                        error_chance=coin_error,
                        delay_chance=coin_delay,
                )

                asyncio.run(sample.operate(self.mock_message))

        mock_random.assert_any_call(min_delay, max_delay)

        mock_sleep.assert_awaited_once_with(5)

        self.mock_logger.debug.assert_called()
        self.mock_logger.info.assert_called_once()

    def test_operate_error(self) -> None:
        min_delay = 2
        max_delay = 10
        coin_error = 10
        coin_delay = 30

        data_provider = {
            'Delay': {'coin': 20, 'error': mproxy.WorkerAwaitError},
            'Error': {'coin': 5, 'error': mproxy.WorkerExecutionError},
        }

        for name, dataset in data_provider.items():
            with self.subTest(f'Test stub worker operate error with data set "{name}"'):
                with unittest.mock.patch('random.randint', autospec=True) as mock_random:
                    with unittest.mock.patch('asyncio.sleep', autospec=True) as mock_sleep:
                        mock_random.side_effect = [5, dataset['coin']]

                        sample = Stub(
                                TestStubWorker.CHANNEL_NAME,
                                logger=self.mock_logger,
                                min_delay=min_delay,
                                max_delay=max_delay,
                                error_chance=coin_error,
                                delay_chance=coin_delay,
                        )

                        with self.assertRaises(dataset['error']):
                            asyncio.run(sample.operate(self.mock_message))

                mock_random.assert_any_call(min_delay, max_delay)
                mock_sleep.assert_awaited_once_with(5)

                self.mock_logger.debug.assert_called()
                self.mock_logger.info.assert_called_once()
                self.mock_logger.reset_mock()


class TestBaseHTTPWorker(unittest.TestCase):
    def test_execute_query(self) -> None:
        url = 'http://example.com/'
        data_provider = {
            'Get text': {'method': 'GET'},
            'Get json': {'method': 'GET', 'content_type': 'application/json'},
            'Post': {'method': 'POST', 'data': {'test': 'value'}},
            'Error request': {'method': 'GET', 'status': 400},
            'Delay request': {'method': 'GET', 'status': 503, 'retry_after': 30},
        }

        text_mock = unittest.mock.Mock()
        json_mock = unittest.mock.AsyncMock()
        headers_mock = unittest.mock.Mock()

        request_mock = unittest.mock.MagicMock()
        request_mock.__aenter__.return_value = request_mock
        request_mock.__aexit__.return_value = request_mock

        for name, data_set in data_provider.items():
            request_data = data_set.get('data')
            status = data_set.get('status', 200)
            content_type = data_set.get('content_type', 'plain/text')
            retry_after = data_set.get('retry_after', None)

            response_data = f'Mock {name}' if content_type == 'plain/text' else {'data': f'Mock {name}'}

            with self.subTest(f'Test test execute query with data set "{name}"'):
                with unittest.mock.patch('aiohttp.ClientTimeout', autospec=True) as timeout:
                    with unittest.mock.patch('aiohttp.ClientSession', autospec=True) as client:
                        client.return_value.__aenter__.return_value.request = request_mock

                        text_mock.return_value = response_data
                        json_mock.return_value = response_data
                        headers_mock.get.return_value = retry_after

                        client.return_value.__aenter__.return_value\
                              .request.return_value.__aenter__.return_value.status = status

                        client.return_value.__aenter__.return_value \
                            .request.return_value.__aenter__.return_value.content_type = content_type

                        client.return_value.__aenter__.return_value \
                            .request.return_value.__aenter__.return_value.text = text_mock

                        client.return_value.__aenter__.return_value \
                            .request.return_value.__aenter__.return_value.json = json_mock

                        client.return_value.__aenter__.return_value \
                              .request.return_value.__aenter__.return_value.headers = headers_mock

                        sample = mproxy.BaseHTTPWorker(url, data_set['method'])

                        response = asyncio.run(sample.execute_query(request_data))

                timeout.assert_called_once()
                client.assert_called_once()

                request_mock.assert_called_once_with(data_set['method'], url, data=request_data)

                if content_type == 'plain/text':
                    text_mock.assert_called_once()
                else:
                    json_mock.assert_awaited_once()

                self.assertEqual(response, {'status': status, 'retry-after': retry_after, 'data': response_data})

            request_mock.reset_mock()
            text_mock.reset_mock()
            json_mock.reset_mock()


class TestTelegramWorker(unittest.TestCase):
    TEST_MESSAGE = 'Test Telegram Message 1'
    CHANNEL_NAME = 'TestChannel'
    URL_EXAMPLE = 'http://example.com/'

    def setUp(self) -> None:
        self.telegram_payload = {
            'text': TestTelegramWorker.TEST_MESSAGE,
            'chat_id': random.randint(100, 10000),
            'disable_notification': False,
        }

        self.bot_id = str(uuid.uuid4())
        self.mock_logger = unittest.mock.Mock(spec=logging.Logger)
        self.mock_message = unittest.mock.Mock(spec=mproxy.Message, text=TestTelegramWorker.TEST_MESSAGE)

    def test_operate(self) -> None:
        with unittest.mock.patch('mproxy.Telegram.execute_query', autospec=True) as base:
            base.return_value = {
                'status': 200,
                'data': {'ok': True, 'result': {'message_id': random.randint(10, 1000)}},
            }

            sample = mproxy.Telegram(
                    TestTelegramWorker.CHANNEL_NAME,
                    bot_id=self.bot_id,
                    chat_id=self.telegram_payload['chat_id'],
                    url=TestTelegramWorker.URL_EXAMPLE,
                    logger=self.mock_logger,
            )

            asyncio.run(sample.operate(self.mock_message))

        base.assert_called_once()

        self.assertEqual(base.call_args.args[1], self.telegram_payload)

        self.mock_logger.debug.assert_called()
        self.mock_logger.info.assert_called()

    def test_operate_fail(self) -> None:
        data_provider = {
            'Stop error': {
                'response': {
                    'status': 400,
                    'data': {'ok': False, 'result': {'description': 'Test no await error'}}, 'retry-after': None,
                },
                'error_type': mproxy.WorkerExecutionError,
            },
            'Retry error from header': {
                'response': {
                    'status': 503,
                    'data': {'ok': False, 'result': {'description': 'Test await error'}}, 'retry-after': 30,
                },
                'error_type': mproxy.WorkerAwaitError,
            },
            'Retry error from body': {
                'response': {
                    'status': 503,
                    'data': {
                        'ok': False,
                        'result': {'description': 'Test await error', 'retry_after': 30},
                    },
                    'retry-after': None,
                },
                'error_type': mproxy.WorkerAwaitError,
            },
        }

        for name, data_set in data_provider.items():
            with self.subTest(f'Test operate fails with data set "{name}"'):
                with unittest.mock.patch('mproxy.Telegram.execute_query', autospec=True) as base:
                    base.return_value = data_set['response']

                    sample = mproxy.Telegram(
                            TestTelegramWorker.CHANNEL_NAME,
                            bot_id=self.bot_id,
                            chat_id=self.telegram_payload['chat_id'],
                            url=TestTelegramWorker.URL_EXAMPLE,
                            logger=self.mock_logger,
                    )

                    with self.assertRaises(data_set['error_type']) as er:
                        asyncio.run(sample.operate(self.mock_message))

                if data_set['error_type'].__name__ == 'mproxy.WorkerAwaitError':
                    self.assertEqual(er.exception.get_delay_in_seconds(), 30)

                base.assert_called_once()
                self.assertEqual(base.call_args.args[1], self.telegram_payload)

                self.mock_logger.debug.assert_called()
                self.mock_logger.warning.assert_called()

                self.mock_logger.reset_mock()


class TestIncrementOrRetryAfterWait(unittest.TestCase):
    MIN_DELAY = 1
    MAX_DELAY = 3600

    def test_call(self) -> None:
        retry_state_mock = unittest.mock.Mock()

        data_provider = {
            'exp': {
                'state': [0, 0, 0, 0, 0, 0, 0, 0],
                'expected': [
                    5, 17, 65,
                    257, 1025,
                    TestIncrementOrRetryAfterWait.MAX_DELAY,
                    TestIncrementOrRetryAfterWait.MAX_DELAY,
                    TestIncrementOrRetryAfterWait.MAX_DELAY,
                ],
            },
            'on retry': {
                'state': [5, 10, 10, 10, 20, 10000, 10000],
                'expected': [
                    5, 10, 10, 10, 20,
                    TestIncrementOrRetryAfterWait.MAX_DELAY, TestIncrementOrRetryAfterWait.MAX_DELAY,
                ],
            },
            'mixed': {
                'state': [5, 0, 10, 0, 20, 10000, 10000],
                'expected': [
                    5, 17, 10, 257, 20,
                    TestIncrementOrRetryAfterWait.MAX_DELAY, TestIncrementOrRetryAfterWait.MAX_DELAY,
                ],
            },
        }

        for name, data_set in data_provider.items():
            retry_state_mock.outcome.exception.return_value.get_delay_in_seconds.side_effect = data_set['state']

            with self.subTest(f'Test IncrementOrRetry with data set "{name}"'):
                result = []
                sample = mproxy.IncrementOrRetryAfterWait(
                        TestIncrementOrRetryAfterWait.MIN_DELAY,
                        TestIncrementOrRetryAfterWait.MAX_DELAY,
                )

                for attempt in range(1, len(data_set['expected']) + 1):
                    retry_state_mock.attempt_number = attempt
                    result.append(sample(retry_state_mock))

                self.assertEqual(result, data_set['expected'])

            retry_state_mock.reset_mock()


class TestVirtualChannel(unittest.TestCase):
    CHANNEL_NAME = 'TestChannel'
    MIN_RETRY_AFTER = 5
    MAX_RETRY_AFTER = 73
    RETRY_ATTEMPTS = 3
    QUEUE_SIZE = 79

    def setUp(self) -> None:
        self.worker_mock = unittest.mock.Mock(spec=mproxy.WorkerInterface)
        self.queue_mock = unittest.mock.Mock(spec=mproxy.QueueInterface)
        self.mock_logger = unittest.mock.Mock(spec=logging.Logger)
        self.mock_task = unittest.mock.Mock(spec=asyncio.Task)

        self.sample = mproxy.VirtualChannel(
                TestVirtualChannel.CHANNEL_NAME,
                self.worker_mock,
                self.queue_mock,
                logger=self.mock_logger,
        )

    def test_create(self) -> None:
        sample = mproxy.VirtualChannel(
                TestVirtualChannel.CHANNEL_NAME,
                self.worker_mock,
                self.queue_mock,
                logger=self.mock_logger,
                min_retry_after=TestVirtualChannel.MIN_RETRY_AFTER,
                max_retry_after=TestVirtualChannel.MAX_RETRY_AFTER,
                retry_attempts=TestVirtualChannel.RETRY_ATTEMPTS,
        )

        self.assertEqual(sample.name, TestVirtualChannel.CHANNEL_NAME)
        self.assertEqual(sample.min_retry_after, TestVirtualChannel.MIN_RETRY_AFTER)
        self.assertEqual(sample.max_retry_after, TestVirtualChannel.MAX_RETRY_AFTER)
        self.assertEqual(sample.retry_attempts, TestVirtualChannel.RETRY_ATTEMPTS)
        self.assertEqual(sample.worker, self.worker_mock)
        self.assertEqual(sample.queue, self.queue_mock)
        self.mock_logger.assert_not_called()

    def test_incorrect_objects_on_create(self) -> None:
        data_provider = {
            'No worker': {'worker': None, 'queue': self.queue_mock},
            'No queue': {'worker': self.worker_mock, 'queue': None},
            'Incorrect worker': {'worker': self, 'queue': self.queue_mock},
            'Incorrect queue': {'worker': self.worker_mock, 'queue': self},
        }

        for name, data_set in data_provider.items():
            with self.subTest(f'Test incorrect virtual channel with data set"{name}"'):
                with self.assertRaises(mproxy.ServerInitError):
                    mproxy.VirtualChannel(
                            data_set['worker'],
                            data_set['queue'],
                            self.queue_mock,
                            logger=self.mock_logger,
                    )

    def test_static_creator(self) -> None:
        self.queue_mock.return_value = self.queue_mock
        self.worker_mock.return_value = self.worker_mock

        side_worker = unittest.mock.Mock(spec=mproxy.WorkerInterface)
        side_worker.return_value = side_worker

        side_queue = unittest.mock.Mock(spec=mproxy.QueueInterface)
        side_queue.return_value = side_queue

        names = {
            'default_queue': 'AIOQueue',
            'default_worker': 'Stub',
            'another_queue': 'SideQueue',
            'another_worker': 'SideWorker',
        }

        workers = {
            names['default_worker']: self.worker_mock,
            names['another_worker']: side_worker,
        }

        queues = {
            names['default_queue']: self.queue_mock,
            names['another_queue']: side_queue,
        }

        def get_queue(item: str, default: mproxy.QueueInterface) -> unittest.mock.Mock:
            if item in queues:
                return queues[item]

            self.assertIsNotNone(default)

            return queues[names['default_queue']]

        def get_worker(item: str, default: mproxy.WorkerInterface) -> unittest.mock.Mock:
            if item in workers:
                return workers[item]

            self.assertIsNotNone(default)

            return workers[names['default_worker']]

        def mock_type(component_type: str) -> unittest.mock.Mock:
            mock = unittest.mock.Mock()

            if component_type == 'workers':
                mock.get.side_effect = get_worker
            elif component_type == 'queues':
                mock.get.side_effect = get_queue

            return mock

        data_provider = {
            'Empty config': {},
            'Default config': {
                'worker': names['default_worker'],
                'queue': names['default_queue'],
                'params': {},
            },
            'Filled config': {
                'worker': names['default_worker'],
                'queue': names['default_queue'],
                'params': {'some': 'params'},
            },
            'Side config': {
                'worker': names['another_worker'],
                'queue': names['another_queue'],
                'queue_size': TestVirtualChannel.QUEUE_SIZE,
                'params': {'some': 'Another params'},
            },
        }

        components = unittest.mock.MagicMock()
        components.__getitem__.side_effect = mock_type

        for name, data_set in data_provider.items():
            with self.subTest(f'Test static creation with data set "{name}"'):
                sample = mproxy.VirtualChannel.create_from_config(
                        TestVirtualChannel.CHANNEL_NAME,
                        data_set,
                        components,
                )

                self.assertEqual(sample.name, TestVirtualChannel.CHANNEL_NAME)

                if data_set.get('worker') == names['another_worker']:
                    self.worker_mock.assert_not_called()
                    side_worker.assert_called_once()
                    self.assertEqual(sample.worker, side_worker)
                else:
                    self.worker_mock.assert_called_once()
                    side_worker.assert_not_called()
                    self.assertEqual(sample.worker, self.worker_mock)

                if data_set.get('queue') == names['another_queue']:
                    self.queue_mock.assert_not_called()
                    side_queue.assert_called_once()
                    self.assertEqual(sample.queue, side_queue)
                else:
                    self.queue_mock.assert_called_once()
                    side_queue.assert_not_called()
                    self.assertEqual(sample.queue, self.queue_mock)

            self.queue_mock.reset_mock()
            self.worker_mock.reset_mock()

            side_worker.reset_mock()
            side_queue.reset_mock()

    def test_get_queue(self) -> None:
        self.assertEqual(self.sample.get_queue(), self.queue_mock)
        self.queue_mock.assert_not_called()

    def test_activate(self) -> None:
        with unittest.mock.patch('mproxy.VirtualChannel.assign_worker'):
            with unittest.mock.patch('asyncio.create_task', autospec=True) as create_mock:
                create_mock.return_value = self.mock_task

                # avoid unnecessary RunTime warning
                async def runner() -> None:
                    await self.sample.activate()

                    await create_mock.call_args.args[0]

                asyncio.run(runner())

                with self.assertRaises(mproxy.RequestExecutionError):
                    asyncio.run(self.sample.activate())

                create_mock.assert_called_once()
                self.assertEqual(self.sample.task, self.mock_task)

                self.mock_logger.debug.assert_called()
                self.mock_logger.info.assert_called()

    def test_deactivate(self) -> None:
        self.sample.task = self.mock_task

        asyncio.run(self.sample.deactivate())

        with self.assertRaises(mproxy.RequestExecutionError):
            asyncio.run(self.sample.deactivate())

        self.mock_task.cancel.assert_called_once()

        self.assertIsNone(self.sample.task)

        self.mock_logger.debug.assert_called()
        self.mock_logger.info.assert_called()

    def test_is_running(self):
        data_provider = {
            'Idle': {'task': None, 'done': None, 'expected': False},
            'Running': {'task': self.mock_task, 'done': False, 'expected': True},
            'Failed': {'task': self.mock_task, 'done': True, 'expected': False},
        }

        for name, data_set in data_provider.items():
            with self.subTest(f'Test is running with data set "{name}"'):
                if data_set['task']:
                    self.mock_task.done.return_value = data_set.get('done', True)

                self.sample.task = data_set['task']

                self.assertEqual(self.sample.is_running, data_set['expected'])

    def test_assign_worker(self):
        worker_data = [None, None, asyncio.CancelledError]

        with unittest.mock.patch('tenacity.retry', autospec=True) as retry_mock:
            self.queue_mock.get_task.return_value = unittest.mock.Mock(spec=mproxy.Message)
            self.worker_mock.operate.side_effect = worker_data

            retry_mock.return_value.side_effect = lambda x: x

            asyncio.run(self.sample.assign_worker())

        retry_mock.assert_called_once()
        retry_mock.return_value.assert_called_once()
        self.worker_mock.operate.assert_called()

        self.assertEqual(self.worker_mock.operate.call_count, len(worker_data))

    def test_assign_worker_stability(self) -> None:
        def check_warning(count: int) -> None:
            self.mock_logger.warning.assert_called()
            self.assertGreaterEqual(self.mock_logger.warning.call_count, count)

        def check_error(count: int) -> None:
            self.mock_logger.error.assert_called()
            self.assertGreaterEqual(self.mock_logger.error.call_count, count)

        def check_info(count: int) -> None:
            self.mock_logger.info.assert_called()
            self.assertGreaterEqual(self.mock_logger.info.call_count, count)

        data_provider = {
            'Worker error': {
                'payload': [
                    mproxy.WorkerExecutionError(400, 'Test'),
                    mproxy.WorkerExecutionError(400, 'Test'),
                    asyncio.CancelledError,
                ],
                'call_count': 3,
                'check': check_error,
                'check_count': 2,
            },
            'Worker incomplete': {
                'payload': [
                    mproxy.WorkerAwaitError(503, 'Test', 30),
                    mproxy.WorkerAwaitError(503, 'Test', 30),
                    asyncio.CancelledError,
                ],
                'call_count': 3,
                'check': check_warning,
                'check_count': 2,
            },
            'Other error': {
                'payload': [Exception('Test'), mproxy.MProxyException('Test'), asyncio.CancelledError],
                'call_count': 3,
                'check': check_warning,
                'check_count': 2,
            },
            'Cancel task': {
                'payload': [asyncio.CancelledError],
                'call_count': 1,
                'check': check_info,
                'check_count': 1,
            },
        }

        for name, data_set in data_provider.items():
            with self.subTest(f'Test assign worker stability with data set"{name}"'):
                with unittest.mock.patch('tenacity.retry', autospec=True) as retry_mock:
                    self.queue_mock.get_task.return_value = unittest.mock.Mock(spec=mproxy.Message)
                    self.worker_mock.operate.side_effect = data_set['payload']

                    retry_mock.return_value.side_effect = lambda x: x

                    asyncio.run(self.sample.assign_worker())

                retry_mock.return_value.assert_called_once()
                self.worker_mock.operate.assert_called()

                self.assertEqual(self.worker_mock.operate.call_count, data_set['call_count'])
                data_set['check'](data_set['check_count'])

            self.worker_mock.reset_mock()
            self.mock_logger.reset_mock()


class TestApplication(unittest.TestCase):
    HOST = 'www.example.com'
    PORT = 11111
    CHANNEL_NAME = 'TestChannel'
    RETRY_AFTER = 27
    MESSAGE_ERROR = 'message error'
    QUEUE_ERROR = 'queue error'
    MAINTENANCE = 'maintenance'
    COMPONENTS = {'queues': {'test': 'queue'}, 'workers': {'test': 'worker'}}

    def setUp(self) -> None:
        self.mock_logger = unittest.mock.Mock(spec=logging.Logger)
        self.channel_mock = unittest.mock.AsyncMock(spec=mproxy.VirtualChannel)

        self.web_app_mock = unittest.mock.MagicMock(spec=Application)

        with unittest.mock.patch('logging.basicConfig', autospec=True):
            self.sample = mproxy.Application(
                    self.web_app_mock,
                    TestApplication.COMPONENTS['queues'],
                    TestApplication.COMPONENTS['workers'],
                    host=TestApplication.HOST,
                    port=TestApplication.PORT,
                    config={TestApplication.CHANNEL_NAME: {}},
                    debug=False,
                    retry_after=TestApplication.RETRY_AFTER,
                    logger=self.mock_logger,
            )

    def test_create(self) -> None:
        config = {TestApplication.CHANNEL_NAME: {}}

        data_provider = {
            'With debug': {'debug': True, 'type': logging.DEBUG},
            'Without debug': {'debug': False, 'type': logging.INFO},
        }

        for name, data_set in data_provider.items():
            with self.subTest(f'Test create with data set "{name}"'):
                with unittest.mock.patch('logging.basicConfig', autospec=True) as log_config:
                    sample = mproxy.Application(
                            self.web_app_mock,
                            TestApplication.COMPONENTS['queues'],
                            TestApplication.COMPONENTS['workers'],
                            host=TestApplication.HOST,
                            port=TestApplication.PORT,
                            config=config,
                            debug=data_set['debug'],
                            retry_after=TestApplication.RETRY_AFTER,
                            logger=self.mock_logger,
                    )

                log_config.assert_called_once()
                self.assertEqual(log_config.call_args.kwargs['level'], data_set['type'])
                self.assertEqual(sample.port, TestApplication.PORT)
                self.assertEqual(sample.host, TestApplication.HOST)
                self.assertEqual(sample.app, self.web_app_mock)
                self.assertEqual(sample._components, TestApplication.COMPONENTS)

                self.web_app_mock.assert_not_called()
                self.mock_logger.info.assert_called()

            self.mock_logger.reset_mock()
            self.web_app_mock.reset_mock()
            self.channel_mock.reset_mock()

    def test_prepare(self) -> None:
        with unittest.mock.patch('mproxy.VirtualChannel.create_from_config', autospec=True) as channel:
            channel.return_value = self.channel_mock

            self.sample.prepare()

        self.web_app_mock.router.add_route.assert_called()
        self.assertGreaterEqual(self.web_app_mock.router.add_route.call_count, 2)
        self.web_app_mock.middlewares.append.assert_called()
        self.assertGreaterEqual(self.web_app_mock.middlewares.append.call_count, 1)

        channel.assert_called_once_with(
                TestApplication.CHANNEL_NAME,
                {},
                TestApplication.COMPONENTS,
                logger=self.mock_logger,
        )

        self.web_app_mock.on_startup.append.assert_called_once()
        self.web_app_mock.on_shutdown.append.assert_called_once()

        self.mock_logger.debug.assert_called()
        self.mock_logger.info.assert_called()

    def test_run(self) -> None:
        with unittest.mock.patch('aiohttp.web.run_app', autospec=True) as web_runner:
            self.sample.run()

        web_runner.assert_called_once_with(self.web_app_mock, host=TestApplication.HOST, port=TestApplication.PORT)

        self.mock_logger.debug.assert_called()

    def test_ping(self) -> None:
        data_provider = {
            'normal': {'state': False, 'response': {'text': 'OK'}},
            'maintenance': {
                'state': True,
                'response': {
                    'text': 'FAIL',
                    'status': 503,
                    'headers': {'Retry-After': str(TestApplication.RETRY_AFTER)},
                },
            },
        }

        request_mock = unittest.mock.Mock(spec=Request)
        request_mock.app = self.web_app_mock

        for name, data_set in data_provider.items():
            self.web_app_mock.__getitem__.return_value = data_set['state']

            with self.subTest(f'Test ping with data set "{name}"'):
                with unittest.mock.patch('aiohttp.web.Response', autospec=True) as response:
                    result = asyncio.run(self.sample.ping(request_mock))

                response.assert_called_once_with(**data_set['response'])
                self.assertEqual(response.return_value, result)

    def test_middleware(self) -> None:
        handler_mock = unittest.mock.AsyncMock()
        request_mock = unittest.mock.Mock(spec=Request)
        response_mock = unittest.mock.Mock(spec=Response)

        handler_mock.return_value = response_mock

        with unittest.mock.patch('aiohttp.web.json_response', autospec=True):
            result = asyncio.run(self.sample.handle_errors_middleware(request_mock, handler_mock))

        handler_mock.assert_awaited_once_with(request_mock)
        self.assertEqual(result, response_mock)

    def test_middleware_catch(self) -> None:
        data_provider = {
            'validation': {'exception': mproxy.RequestParameterError('Test'), 'should_raise': False, 'code': 422},
            'unavailable': {'exception': mproxy.TemporaryUnawailableError('Test'), 'should_raise': False, 'code': 503},
            'http': {'exception': HTTPException, 'should_raise': True},
            'app error': {'exception': mproxy.MProxyException('Test'), 'should_raise': False, 'code': 500},
            'other error': {'exception': Exception('Test'), 'should_raise': False, 'code': 500},
        }

        response_data = {'status': 'error', 'error': 'Test'}

        handler_mock = unittest.mock.AsyncMock()
        request_mock = unittest.mock.Mock(spec=Request)

        for name, data_set in data_provider.items():
            with self.subTest(f'Test middleware catch with data set "{name}"'):
                with unittest.mock.patch('aiohttp.web.json_response', autospec=True) as response_mock:
                    handler_mock.side_effect = data_set['exception']

                    if data_set['should_raise']:
                        with self.assertRaises(HTTPException):
                            asyncio.run(self.sample.handle_errors_middleware(request_mock, handler_mock))
                    else:
                        asyncio.run(self.sample.handle_errors_middleware(request_mock, handler_mock))

                        response_mock.assert_called_once_with(response_data, status=data_set['code'])

                    handler_mock.assert_awaited_once_with(request_mock)

            handler_mock.reset_mock()

    def test_send_message(self) -> None:
        test_data = {'text': 'Test sample', 'delay': '7'}
        request_mock = unittest.mock.Mock(spec=Request)
        message_mock = unittest.mock.Mock(spec=mproxy.Message)

        request_mock.match_info.get.return_value = TestApplication.CHANNEL_NAME
        request_mock.post = unittest.mock.AsyncMock(return_value=test_data)

        request_mock.app = self.web_app_mock
        self.web_app_mock.__getitem__.return_value = False

        self.channel_mock.is_running.__bool__.return_value = True

        self.sample.channels = {TestApplication.CHANNEL_NAME: self.channel_mock}

        with unittest.mock.patch('mproxy.Message.extract_from_request_data', autospec=True) as message:
            with unittest.mock.patch('aiohttp.web.json_response', autospec=True) as response:

                response.return_value = response
                message.return_value = message_mock

                result = asyncio.run(self.sample.send_message(request_mock))

        self.channel_mock.is_running.__bool__.assert_called_once()
        self.channel_mock.get_queue.return_value.add_task.assert_called_once_with(message_mock, int(test_data['delay']))

        request_mock.post.assert_awaited_once()
        message.assert_called_once_with(test_data)

        response.assert_called_once_with({'status': 'success'})
        self.assertEqual(result, response)

        self.mock_logger.debug.assert_called()

    def test_send_message_fails(self) -> None:
        data_provider = {
            'no channel': {'exception': mproxy.RequestParameterError, 'channel': 'SomeChannel'},
            'inactive channel': {'exception': mproxy.TemporaryUnawailableError, 'running': False},
            'no data': {'exception': mproxy.RequestParameterError, 'effect': TestApplication.MESSAGE_ERROR},
            'queue full': {'exception': mproxy.TemporaryUnawailableError, 'effect': TestApplication.QUEUE_ERROR},
            'maintenance': {'exception': mproxy.TemporaryUnawailableError, 'effect': TestApplication.MAINTENANCE},
        }

        message_mock = unittest.mock.Mock(spec=mproxy.Message)
        request_mock = unittest.mock.Mock(spec=Request)
        request_mock.post = unittest.mock.AsyncMock(return_value={'text': 'Test sample', 'delay': '7'})
        request_mock.app = self.web_app_mock

        self.sample.channels = {TestApplication.CHANNEL_NAME: self.channel_mock}

        for name, data_set in data_provider.items():
            request_mock.match_info.get.return_value = data_set.get('channel', TestApplication.CHANNEL_NAME)
            self.channel_mock.is_running.__bool__.return_value = data_set.get('running', True)

            with self.subTest(f'Test send message fails with data set "{name}"'):
                with unittest.mock.patch('mproxy.Message.extract_from_request_data') as message:
                    with unittest.mock.patch('aiohttp.web.json_response'):
                        effect = data_set.get('effect')

                        if effect == TestApplication.MAINTENANCE:
                            self.web_app_mock.__getitem__.return_value = True
                        else:
                            self.web_app_mock.__getitem__.return_value = False

                        if effect == TestApplication.MESSAGE_ERROR:
                            message.side_effect = data_set['exception']
                        else:
                            message.return_value = message_mock

                        if effect == TestApplication.QUEUE_ERROR:
                            self.channel_mock.get_queue.side_effect = data_set['exception']
                        else:
                            self.channel_mock.get_queue.side_effect = None

                        with self.assertRaises(data_set['exception']):
                            asyncio.run(self.sample.send_message(request_mock))

            self.channel_mock.reset_mock()


if __name__ == '__main__':
    unittest.main()
