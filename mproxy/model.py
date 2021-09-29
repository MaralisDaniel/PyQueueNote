from __future__ import annotations
from multidict import MultiDictProxy

from .exceptions import RequestParameterError


class Message:
    def __init__(self, *, text=None, header=None, payload=None):
        self.text = text
        self.header = header
        self.payload = payload

    @classmethod
    def extract_from_request_data(cls, data: MultiDictProxy, *, required: bool = True, default: dict = None) -> Message:
        default = default or {}
        result = {}

        for key in ['text', 'header', 'payload']:
            result[key] = data.get(key, default.get(key))

        if required and not any(result.values()):
            raise RequestParameterError('Message could not empty')

        return cls(**result)

    def __repr__(self):
        payload_count = '' if self.payload is None else 'not '

        return f'Message header: {self.header}, text: {self.text}, payload is {payload_count}empty'
