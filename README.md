Py-Message-Proxy
=========

## Overview

From the box this service allows you to send simple messages to Telegram with help of http-proxy in "fire-and-forget" way: proxy will deal with delivery of message to Telegram itself. You may create different configurations (virtual channels) to send messages with different params (for example, chat, bot, local API server url etc.). Py-Message-Proxy (m-proxy in shorthand) contains from library which do all job by querying Telegram API (mproxy package) and simple cli-runner (main.py script). Library allows you to include it in your app, add your own workers (if you need to send messages to other messengers), add your own queues (if default in-memory queue doesn't satisfy your requirements, and, for example, you need persistent queue)

### Build-in usage

To run build-in server you should install all requirements (you are free to use pip or sync with help of pipenv, it's also possible to run _make_ command with _setup_ argument). After all requirements are installed you should create configuration file: you can just copy _config.example.yaml_, remove _example_ from its name and modify it for your own (_config.yaml_ is git ignored file). Next just run _main.py_ file with required args - you may see them by running "main.py" with _-h_ or _--help_


### Docker image

M-proxy contains Dockerfile - just build it and run. There are 3 env args available:
- CONFIG: config filename, default value - "config.example.yaml"
- HOST: ip or domain name to listen for incoming messages, default value - "127.0.0.1"
- PORT: port to listen on selected ip or domain name, default value "8080"

_Tip: running docker container on "127.0.0.1" will not allow you to connect to m-proxy from net - you should specify this param to use service (in simple way pass 0.0.0.0, but remember - this is insecure)_

## HTTP-Api

### Ping service

Simple route to check that service is running

- route: \<host or domain\>/api/ping
- allowed method: GET
- return Content-type: plain/text
- on call will return text "OK" if service is running

### Send messages

Primary build-in http-api route - allows you to send messages to specified virtual channel

- route: \<host or domain\>/api/send/\<channel-name\>
- allowed method: POST
- route parameter: channel-name, name of selected channel
- return Content-type: application/json
- on call will return JSON contains status of request and description in case of error
- body:
   - message, required, JSON object of the message
   - delay, optional, time in seconds to delay message delivery (not implemented yet)
