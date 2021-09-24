import mproxy


def main() -> None:
    args = mproxy.CLIRunner(
            prog='Message HTTP proxy',
            description='HTTP-proxy server for serving message delivery with help of virtual channels',
            epilog='Note: all of those arguments has its defaults',
    ).parse_args()

    app = mproxy.Application(
            host=args.host,
            port=args.port,
            config_filename=args.config,
            debug=args.debug,
    )

    app.init()
    app.run()


if __name__ == '__main__':
    main()
