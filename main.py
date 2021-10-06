import argparse
import yaml

import mproxy


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

    def error(self, message: str):
        self._print_message(f'{self.prog} - error: {message}')
        self.print_help()
        self.exit(2)


def main() -> None:
    args = ArgParser(
            prog='Message HTTP proxy',
            description='HTTP-proxy server for serving message delivery with help of virtual channels',
            epilog='Note: all of those arguments has its defaults',
    ).parse_args()

    config = yaml.safe_load(args.config)

    args.config.close()

    app = mproxy.Application(
            {'AIOQueue': mproxy.queues.AIOQueue},
            {'Stub': mproxy.workers.Stub, 'Telegram': mproxy.workers.Telegram},
            host=args.host,
            port=args.port,
            config=config,
            debug=args.debug,
    )

    app.prepare()
    app.run()


if __name__ == '__main__':
    main()
