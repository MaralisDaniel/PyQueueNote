import argparse

import yaml
from aiohttp import web

import mproxy
from tests.stubs import Stub

QUEUES = {'AIOQueue': mproxy.queues.AIOQueue}
WORKERS = {'Stub': Stub, 'Telegram': mproxy.workers.Telegram}


class ArgParser(argparse.ArgumentParser):
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
                type=argparse.FileType('r'),
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

        self.add_argument(
                '--show_queues',
                help='List available queue names which could be used in config file and exit',
                action='store_true',
                dest='queues',
        )

        self.add_argument(
                '--show_workers',
                help='List available workers names which could be used in config file and exit',
                action='store_true',
                dest='workers',
        )

    def error(self, message: str):
        self._print_message(f'{self.prog} - error: {message}')
        self.print_help()
        self.exit(2)


def show_available_workers():
    print('Available workers:', '')

    for name, worker in WORKERS.items():
        print(name)

        if worker.__doc__:
            print(worker.__doc__, '')
        else:
            print('No description for this worker', '')


def show_available_queues():
    print('Available queues')

    for name, queue in QUEUES.items():
        print(name)

        if queue.__doc__:
            print(queue.__doc__, '')
        else:
            print('No description for this queue', '')


def main() -> None:
    args = ArgParser(
            prog='Message HTTP proxy',
            description='HTTP-proxy server for serving message delivery with help of virtual channels',
            epilog='Note: all of those arguments has its defaults',
    ).parse_args()

    if args.workers:
        show_available_workers()

    if args.queues:
        show_available_queues()

    if args.queues or args.workers:
        exit(0)

    config = yaml.safe_load(args.config)

    args.config.close()

    app = mproxy.Application(
            web.Application(),
            QUEUES,
            WORKERS,
            host=args.host,
            port=args.port,
            config=config,
            debug=args.debug,
    )

    app.run()


if __name__ == '__main__':
    main()
