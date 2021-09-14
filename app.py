from aiohttp import web
from Controller import Controller
from Validation import Validator
from Config import Config
import Service

app = web.Application()
config = Config()
controller = Controller(Validator(), Service.VCollection(config.get_raw()['v-channels']))

app['config'] = config

app.add_routes([
    web.post('/api/send/{channel:\\w+}', controller.send_message),
    web.get('/api/ping', controller.ping)
])

if __name__ == '__main__':
    web.run_app(app, host=config.get('server.host'), port=config.get('server.port'))
