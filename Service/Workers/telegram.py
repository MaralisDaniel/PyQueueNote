import aiohttp
from ..Queues.AbstractQueue import AbstractQueue


def get_worker(channel: str, config: dict) -> callable:
    bot_id = config.get('bot_id')
    chat_id = config.get('chat_id')
    host = config.get('host')
    parse_mode = config.get('parse_mode')
    notify = config.get('notify')

    if bot_id is None or chat_id is None or host is None:
        raise NameError('Required for operating parameters bot_id or host or chat_id is not presented in configuration')

    if not host.endswith('/'):
        host += '/'

    data = {'chat_id': chat_id}
    pattern = '/.{1,4096}/uims'

    if parse_mode is not None:
        data['parse_mode'] = parse_mode

    if notify is not None:
        data['disable_notification'] = not notify

    async def worker(queue: AbstractQueue) -> None:
        while True:
            data['text'] = await queue.get_task()

            async with aiohttp.request(
                    'POST',
                    f'{host}bot{bot_id}/sendMessage',
                    data=data
            ) as result:
                response = await result.json()

                # TODO manage normal debug/logging
                if result.status == 200 and response['ok']:
                    print(f'Channel {channel} accepted the message, its id: {response["result"]["message_id"]}')
                else:
                    # TODO add normal error handling
                    print(f'Channel {channel} declined the message, '
                          f'status: {result.status}, reason: {response.get("description")}')

            queue.complete()

    return pattern, worker
