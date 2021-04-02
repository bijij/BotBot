import datetime

from collections import defaultdict

from typing import Any, Callable


__all__ = ('LRUDict', 'LRUDefaultDict')


class TimedDict(dict):

    def __init__(self, expires_after: datetime.timedelta, *args, **kwargs):
        self.expires_after = expires_after
        self._state = {}
        super().__init__(*args, **kwargs)

    def __cleanup(self):
        now = datetime.datetime.utcnow()
        for key in list(super().keys()):
            try:
                delta = now - self._state[key]
                if delta > self.expires_after:
                    del self[key]
                    del self._state[key]
            except KeyError:
                pass

    def __setitem__(self, key: Any, value: Any):
        super().__setitem__(key, value)
        self._state[key] = datetime.datetime.utcnow()

    def __getitem__(self, key: Any) -> Any:
        self.__cleanup()
        return super().__getitem__(key)


class LRUDict(dict):

    def __init__(self, max_size: int = 1024, *args, **kwargs):
        if max_size <= 0:
            raise ValueError('Maximum cache size must be greater than 0.')
        self.max_size = max_size
        super().__init__(*args, **kwargs)
        self.__cleanup()

    def __cleanup(self):
        while len(self) > self.max_size:
            del self[next(iter(self))]

    def __getitem__(self, key: Any) -> Any:
        value = super().__getitem__(key)
        self.__cleanup()
        return value

    def __setitem__(self, key: Any, value: Any):
        super().__setitem__(key, value)
        self.__cleanup()


class TimedLRUDict(LRUDict, TimedDict):

    def __init__(self, expires_after: datetime.timedelta, max_size: int = 1024, *args, **kwargs):
        super().__init__(max_size, expires_after, *args, **kwargs)


class LRUDefaultDict(LRUDict, defaultdict):

    def __init__(self, default_factory: Callable = None, max_size: int = 1024, *args, **kwargs):
        super().__init__(max_size, *args, **kwargs)
        self.default_factory = default_factory


class TimedLRUDefaultDict(LRUDict, TimedDict, defaultdict):

    def __init__(self, default_factory: Callable, expires_after: datetime.timedelta, max_size: int = 1024, *args, **kwargs):
        super().__init__(expires_after, max_size, *args, **kwargs)
        self.default_factory = default_factory
