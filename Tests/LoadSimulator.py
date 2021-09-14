import aiohttp
import asyncio
from datetime import datetime
from Config import Config


def get_load(channels: list, *, message_count=3) -> list:
    result = []

    for channel in channels:
        for message_index in range(1, message_count + 1):
            result.append({'channel': channel, 'message': f'Payload number {message_index} for channel {channel}'})

    return result


async def send_message(message: str, url: str) -> None:
    print(f'At {datetime.now().strftime("%H:%M:%S.%f")} request started')

    async with aiohttp.request('POST', url, data={'message': message}) as response:
        print(f'At {datetime.now().strftime("%H:%M:%S.%f")} request finished, response code {response.status}')


async def emulate_payload(url: str, channels: list, message_count: int) -> None:
    for payload in get_load(channels, message_count=message_count):
        await send_message(payload['message'], url + payload['channel'])


def run(channels, message_count=3) -> None:
    print(f'Run at {datetime.now().strftime("%H:%M:%S.%f")}')

    if isinstance(channels, str):
        channels = [channels]
    elif not isinstance(channels, list):
        channels = ['stub']

    config = Config()

    url_stub = f"{config.get('server.host')}:{config.get('server.port')}"

    if not url_stub.startswith('http'):
        url_stub = 'http://' + url_stub

    if not url_stub.endswith('/'):
        url_stub += '/'

    asyncio.run(emulate_payload(url_stub + 'api/send/', channels, message_count))

    print(f'End at {datetime.now().strftime("%H:%M:%S.%f")}')
