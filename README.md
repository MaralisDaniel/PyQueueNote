Py-Message-Proxy
=========

## Overview

From the box this service allows you to send simple messages to Telegram with help of http-proxy in "fire-and-forget" way: proxy will deal with delivery of message to Telegram itself. You may create different configurations (virtual channels) to send messages with different params (for example, chat, bot, local API server url etc.). Py-Message-Proxy (m-proxy in shorthand) contains library which do all job by querying Telegram API (mproxy package) and simple cli-runner (main.py script). Library allows you to include it in your app, add your own workers (if you need to send messages to other messengers or services), add your own queues (if default in-memory queue doesn't satisfy your requirements, and you need persistent queue for example)

### Build-in usage

To run build-in server you should install all requirements (you are free to use pip or pipenv sync, it's also possible to run _make_ command, see makefile):

`make setup` or `pip install -r requirements.txt` or `pipenv sync`


After all requirements are installed you should create a configuration file: just copy _config.example.yaml_, remove _example_ suffix from its name and modify it for your own:

`cp config.example.yaml config.yaml`

_Tip: config.yaml is git ignored file_

Next run _main.py_ script with required args - you may learn them by running _main.py_ with _-h_ or _--help_ option:

`mproxy_server.py` to run app

`mproxy_server.py -h` to view help on app

`mproxy_server.py --show_workers --show_queues` to view available workers and queues description and class names

### Docker image

M-proxy contains Dockerfile - you can build it and run image. There are 3 env args are available:
- **CONFIG**: config filename, default value - _config.example.yaml_

In case if you are using ready container from repository you can bind any suitable config file and pass route as CONFIG env param, for example:

`docker run -e CONFIG='/var/mproxy/config.yaml' -dp 8080:8080 --mount='type=bind,source=/some/path/config.yaml,target=/var/mproxy/config.yaml' m-proxy`

## HTTP-Api

### Ping service

Simple route to check that service is running

- route: **\<host or domain\>/api/ping**
- allowed method: **GET**
- return Content-type: **plain/text**
- on call will return text "OK" if service is running

#### Example

Request on _localhost_:

`curl -X GET http://localhost/api/ping`

Response:

`OK`

### Send messages

Primary build-in http-api route - allows you to send messages to specified virtual channel

- route: **\<host or domain\>/api/send/\<channel-name\>**
- allowed method: **POST**
- allowed Content-type: **application/json**
- route parameter: **channel-name**, name of selected channel
- return Content-type: **application/json**
- on call will return JSON contains status of request and description in case of error
- body should contain JSON object:
   - **message**, required, formatted message
   - **params**, optional, options of this message that should be passed with message (parse mode or disable notification for example). This params depends on outer service you are actually calling
   - **delay**, optional, time in seconds to delay message delivery (not implemented yet)

#### Example

Request on _localhost_:

`curl -H 'Content-type: application/json' -d '{"message": "Test"}' -X POST http://localhost/api/send/Stub`

Response:

`{"status": "success"}`

### Get channel stat

Monitor route - allows you to view stats and last error of specified virtual channel

- route: **\<host or domain\>/api/stat/\<channel-name\>**
- allowed method: **GET**
- route parameter: **channel-name**, name of selected channel
- return Content-type: **application/json**
- on call will return JSON contains stat of this channel, running or not and last error in case it has occurs

#### Example

Request on _localhost_:

`curl -X GET http://localhost/api/stat/Stub`

Response:

`{"status": "success"}`

## Config

Configuration file is required for build-in app to operate. It is simple _YAML_ file where you should specify virtual channels parameters. Each channel has two groups of parameters: for worker of this channel and for queue of this channel. Also, you can specify retry options. Config file's structure:

```
channel_name:
   - worker_params:
      - worker_class_name
      - other_params (specified by worker)
   - queue_params:
      - queue_class_name
      - other_params (specified by queue)
   - retry_options
```

_Tip: All optional and required parameters and class names of build-in queues and workers may be viewed by calling app with --show_queues and --show_workers respectively_

There is also an example file in the root directory with comments to some parameters
