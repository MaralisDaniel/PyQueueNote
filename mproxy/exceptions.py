from typing import Union
from datetime import datetime


class MProxyException(Exception):
    pass


class RequestExecutionError(MProxyException):
    pass


class RequestParameterError(MProxyException):
    pass


class ServerIsRunningError(MProxyException):
    pass


class ServerInitError(MProxyException):
    pass


class TemporaryUnawailableError(MProxyException):
    pass


class WorkerAwaitError(MProxyException):
    def __init__(self, state: int, reason: str, *args, delay: Union[str, int] = None, **kwargs):
        super().__init__(args, kwargs)

        self._state = state
        self._reason = reason
        self._delay = 0 if delay is None else delay

    def get_delay_in_seconds(self):
        try:
            diff = datetime.strptime(str(self._delay), '%a, %d %b %Y %H:%M:%S %Z') - datetime.now()

            delay = max(0, diff.seconds + diff.days * 86400)
        except ValueError:
            delay = int(self._delay)
        except Exception:
            raise

        return delay

    def __repr__(self):
        return f'Worker execution error, applicable for retry, response state: {self._state}, reason: {self._reason}'


class WorkerExecutionError(MProxyException):
    def __init__(self, state: int, reason: str, *args, **kwargs):
        super().__init__(args, kwargs)

        self._state = state
        self._reason = reason

    def __repr__(self):
        return f'Worker execution error, useless for retry, response state: {self._state}, reason: {self._reason}'
