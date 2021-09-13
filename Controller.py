from aiohttp import web
from Exceptions import ValidationException


class Controller:
    __validator = None
    __v_collection = None

    def __init__(self, validator, v_collection):
        self.__validator = validator
        self.__v_collection = v_collection

    async def send_message(self, request):
        try:
            data = {'channel': request.match_info['channel'], **(await self.__get_data(request, ('message', 'delay')))}

            valid_data = self.__validator.exec(data, {'channel': 'required|string', 'delay': 'nullable|number'})

            if not self.__v_collection.is_channel(valid_data['channel']):
                raise ValidationException(f"Virtual channel {valid_data['channel']} is not registered in service")

            message_pattern = self.__v_collection.get_pattern(valid_data['channel'])

            valid_data.update(self.__validator.exec(data, {'message': f'required|regex:{message_pattern}'}))

            self.__v_collection.add_task(valid_data['channel'], valid_data['message'])

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
