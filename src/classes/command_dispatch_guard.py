"""Synchronous admission at the last application-owned command boundary."""

from enum import Enum
import inspect
import json
import re
from typing import Callable


class DispatchRefusalKind(str, Enum):
    SUPERSEDED = "superseded"
    TERMINAL = "terminal"


class DispatchRefused(RuntimeError):
    """A command admission refusal, before dispatch or confirmed by its backend."""

    def __init__(self, reason_code: str, kind: DispatchRefusalKind, *, details: dict | None = None) -> None:
        if (not isinstance(reason_code, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,127}", reason_code) is None
                or not isinstance(kind, DispatchRefusalKind)):
            raise ValueError("dispatch_refusal_contract_invalid")
        self.reason_code = reason_code
        self.kind = kind
        try:
            if details is not None and not isinstance(details, dict):
                raise ValueError("dispatch_refusal_details_invalid")
            self._details_json = None if details is None else json.dumps(details, allow_nan=False)
        except (ValueError, TypeError) as error:
            raise ValueError("dispatch_refusal_details_invalid") from error
        super().__init__(reason_code)

    @property
    def details(self) -> dict | None:
        return None if self._details_json is None else json.loads(self._details_json)


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
