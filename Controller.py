from aiohttp import web
from Exceptions import ValidationException


class Controller:
    def __init__(self, validator):
        self.validator = validator

    async def send_message(self, request):
        try:
            data = {'channel': request.match_info['channel'], **(await self.__get_data(request, ('message', 'delay')))}

            valid_data = self.validator.exec(data, {'channel': 'required|string', 'delay': 'nullable|number'})

            # TODO mock for worker regex - change it after worker implements
            mock = '/[\\wа-я\\s]+/iu'

            valid_data['message'] = self.validator.exec(data, {'message': 'required|regex:' + mock})

            # TODO put task in queue

            return web.Response(status=204, content_type='')
        except ValidationException as e:
            return web.json_response({'error': str(e)}, status=422)
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def ping(self, request) -> web.Response:
        response = web.Response(content_type='plain/text', charset='utf-8')

        # TODO: for first steps it will return only OK status, after adding maintenance mode - modify it

        response.text = 'OK'
        response.set_status(200)

        return response

    async def __get_data(self, request, keys=()):
        result = {}

        if request.body_exists and request.can_read_body:
            post_data = await request.post()
        else:
            post_data = {}

        for key in keys:
            if key in post_data:
                result[key] = post_data[key]
            else:
                result[key] = request.query.get(key)

        return result
