from collections import defaultdict

from typing import Any, Callable


__all__ = ('LRUDict', 'LRUDefaultDict')


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


class LRUDefaultDict(LRUDict, defaultdict):

    def __init__(self, default_factory: Callable = None, max_size: int = 1024, *args, **kwargs):
        super().__init__(max_size, *args, **kwargs)
        self.default_factory = default_factory
