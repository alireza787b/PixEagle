"""Execution helpers for API work that must not block the ASGI event loop."""

from __future__ import annotations

from functools import wraps
from typing import Awaitable, Callable, ParamSpec, TypeVar

from starlette.concurrency import run_in_threadpool


P = ParamSpec("P")
R = TypeVar("R")


def offload_blocking_route(
    function: Callable[P, R],
) -> Callable[P, Awaitable[R]]:
    """Keep one complete synchronous transaction on a single worker thread."""

    @wraps(function)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return await run_in_threadpool(function, *args, **kwargs)

    return wrapper
