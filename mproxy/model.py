from __future__ import annotations

import uuid

from typing import Union

from multidict import MultiDictProxy

from .exceptions import RequestParameterError


class Message:
    FIELDS = ('text', 'header', 'payload')

    def __init__(self, *, text=None, header=None, payload=None):
        self.text = text
        self.header = header
        self.payload = payload
        self.id = uuid.uuid4()

    @classmethod
    def extract_from_request_data(
            cls,
            data: Union[MultiDictProxy | dict],
            *,
            required: bool = True,
            default: dict = None
    ) -> Message:
        default = default or {}
        result = {}

        for key in Message.FIELDS:
            result[key] = data.get(key, default.get(key))

        if required and not any(result.values()):
            raise RequestParameterError('Message could not empty')

        return cls(**result)

    def __repr__(self):
        payload_count = '' if self.payload is None else 'not '
        header = '' if self.header is None else self.header
        text = '' if self.text is None else self.text

        return f'Message header: "{header}", text: "{text}", payload is {payload_count}empty'
