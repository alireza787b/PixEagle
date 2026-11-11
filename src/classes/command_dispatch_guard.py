"""Synchronous admission at the last application-owned command boundary."""

from enum import Enum
import inspect
import re
from typing import Callable


class DispatchRefusalKind(str, Enum):
    SUPERSEDED = "superseded"
    TERMINAL = "terminal"


class DispatchRefused(RuntimeError):
    """A pre-dispatch refusal, independently of transport acknowledgement."""

    def __init__(self, reason_code: str, kind: DispatchRefusalKind) -> None:
        if (not isinstance(reason_code, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,127}", reason_code) is None
                or not isinstance(kind, DispatchRefusalKind)):
            raise ValueError("dispatch_refusal_contract_invalid")
        self.reason_code = reason_code
        self.kind = kind
        super().__init__(reason_code)


def validate_before_dispatch(callback: Callable[[], None] | None) -> None:
    if callback is None:
        return
    if not callable(callback):
        raise DispatchRefused("dispatch_guard_contract_invalid", DispatchRefusalKind.TERMINAL)
    try:
        result = callback()
    except DispatchRefused:
        raise
    except Exception as error:
        raise DispatchRefused("dispatch_guard_failed", DispatchRefusalKind.TERMINAL) from error
    if result is not None:
        if inspect.iscoroutine(result):
            result.close()
        raise DispatchRefused("dispatch_guard_contract_invalid", DispatchRefusalKind.TERMINAL)
