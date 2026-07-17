"""Shared publication barrier for coherent runtime configuration reads."""

from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
import threading
from typing import Any, Callable, Iterator


@dataclass
class RuntimeConfigPublication:
    """One publication attempt guarded by :class:`RuntimeConfigBarrier`."""

    generation_before: int
    _committed: bool = False

    def commit(self) -> None:
        """Mark this publication successful so its generation is advanced."""
        self._committed = True


class RuntimeConfigBarrier:
    """Serialize runtime-config publication and coherent reader snapshots."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._generation = 0

    @contextmanager
    def read(self) -> Iterator[int]:
        """Hold a coherent runtime-config generation for one or more reads."""
        with self._lock:
            yield self._generation

    @contextmanager
    def publish(self) -> Iterator[RuntimeConfigPublication]:
        """Hold the publication barrier and advance once after explicit commit."""
        with self._lock:
            publication = RuntimeConfigPublication(self._generation)
            yield publication
            if publication._committed:
                self._generation += 1

    def generation(self) -> int:
        """Return the latest completely published generation."""
        with self._lock:
            return self._generation


runtime_config_barrier = RuntimeConfigBarrier()


def manager_runtime_config_reader(function: Callable[..., Any]) -> Callable[..., Any]:
    """Guard a manager getter with the shared barrier and its reentrant lock."""

    @wraps(function)
    def guarded(instance: Any, *args: Any, **kwargs: Any) -> Any:
        with runtime_config_barrier.read():
            with instance._lock:
                return function(instance, *args, **kwargs)

    return guarded
