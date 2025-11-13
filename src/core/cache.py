from __future__ import annotations

from collections import OrderedDict
from typing import Generic, MutableMapping, Optional, TypeVar


K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """Simple LRU cache for in-memory data such as thumbnails."""

    def __init__(self, maxsize: int = 128):
        self.maxsize = maxsize
        self._data: MutableMapping[K, V] = OrderedDict()

    def get(self, key: K) -> Optional[V]:
        if key not in self._data:
            return None
        value = self._data.pop(key)
        self._data[key] = value
        return value

    def set(self, key: K, value: V) -> None:
        if key in self._data:
            self._data.pop(key)
        elif len(self._data) >= self.maxsize:
            self._data.popitem(last=False)
        self._data[key] = value

    def clear(self) -> None:
        self._data.clear()
