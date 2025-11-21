"""
Lightweight event bus for cross-page notifications without tight coupling.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List


class EventBus:
    """Simple pub/sub event bus."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable) -> None:
        self._subscribers[event].append(callback)

    def emit(self, event: str, *args, **kwargs) -> None:
        for cb in list(self._subscribers.get(event, [])):
            try:
                cb(*args, **kwargs)
            except Exception:
                # Swallow callbacks errors to avoid cascading failures
                continue
