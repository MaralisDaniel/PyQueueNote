from __future__ import annotations

import uuid
from typing import Union

from multidict import MultiDictProxy

from .exceptions import RequestParameterError


class BaseMessage:
    def __init__(self, message: str = None, delay: int = None, params: dict = None):
        self.message = message
        self.params = params or {}
        self.delay = delay
        self.id = uuid.uuid4()

    @classmethod
    def extract_from_request_data(cls, data: Union[MultiDictProxy, dict], required: bool = True, default: dict = None) -> BaseMessage:
        default = default or {}
        result = {
            'message': data.get('message', default.get('message')),
            'params': data.get('params', default.get('params', {})),
            'delay': data.get('delay', default.get('delay', 0)),
        }
        if required and not result['message']:
            raise RequestParameterError('Message could not empty')
        return cls(**result)

    def __repr__(self):
        return f'Message with id {self.id}'
