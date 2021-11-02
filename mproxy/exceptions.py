from typing import Union


class MProxyException(Exception):
    pass


class RequestExecutionError(MProxyException):
    pass


class RequestParameterError(MProxyException):
    pass


class TemporaryUnawailableError(MProxyException):
    pass


class WorkerAwaitError(MProxyException):
    def __init__(self, state: int, reason: str, delay: Union[str, int, float] = None):
        self._state = state
        self._reason = reason
        self.delay = delay

    def __repr__(self):
        return f'Worker execution error, applicable to retry, response state: {self._state}, reason: {self._reason}'


class WorkerExecutionError(MProxyException):
    def __init__(self, state: int, reason: str):
        self._state = state
        self._reason = reason

    def __repr__(self):
        return f'Worker execution error, useless to retry, response state: {self._state}, reason: {self._reason}'
