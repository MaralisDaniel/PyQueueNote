import math
from datetime import datetime, timezone
from typing import Union


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
            delay_value = str(self._delay)

            if delay_value.endswith('GMT'):
                diff = datetime.strptime(delay_value, '%a, %d %b %Y %H:%M:%S %Z') - datetime.now()
            else:
                if delay_value.endswith('UTC'):
                    delay_value = delay_value.replace('UTC', '+0000')

                diff = datetime.strptime(delay_value, '%a, %d %b %Y %H:%M:%S %z') - datetime.now(timezone.utc)

            delay = max(0, math.ceil(diff.microseconds/1000000) + diff.seconds + diff.days * 86400)
        except ValueError:
            delay = int(self._delay)
        except Exception:
            raise

        return delay

    def __repr__(self):
        return f'Worker execution error, applicable to retry, response state: {self._state}, reason: {self._reason}'


class WorkerExecutionError(MProxyException):
    def __init__(self, state: int, reason: str, *args, **kwargs):
        super().__init__(args, kwargs)

        self._state = state
        self._reason = reason

    def __repr__(self):
        return f'Worker execution error, useless to retry, response state: {self._state}, reason: {self._reason}'
