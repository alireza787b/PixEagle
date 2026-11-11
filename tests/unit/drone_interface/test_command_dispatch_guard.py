import asyncio

import pytest

from classes.command_dispatch_guard import (
    DispatchRefusalKind, DispatchRefused, validate_before_dispatch,
)


def test_optional_guard_and_synchronous_void_callback():
    calls = []
    validate_before_dispatch(None)
    validate_before_dispatch(lambda: calls.append("checked"))
    assert calls == ["checked"]


@pytest.mark.parametrize("kind", list(DispatchRefusalKind))
def test_typed_refusal_is_preserved(kind):
    refusal = DispatchRefused("target_replaced", kind)

    def reject():
        raise refusal

    with pytest.raises(DispatchRefused) as error:
        validate_before_dispatch(reject)
    assert error.value is refusal
    assert error.value.reason_code == "target_replaced"
    assert error.value.kind is kind


@pytest.mark.parametrize("callback", [1, lambda: True, lambda: 0, lambda: object()])
def test_invalid_guard_contract_fails_closed(callback):
    with pytest.raises(DispatchRefused, match="dispatch_guard_contract_invalid") as error:
        validate_before_dispatch(callback)
    assert error.value.kind is DispatchRefusalKind.TERMINAL


def test_async_guard_is_closed_without_running():
    calls = []

    async def invalid():
        calls.append("ran")

    coroutine = invalid()
    with pytest.raises(DispatchRefused, match="dispatch_guard_contract_invalid"):
        validate_before_dispatch(lambda: coroutine)
    assert coroutine.cr_frame is None
    assert calls == []


def test_guard_failure_is_terminal_but_cancellation_propagates():
    def broken():
        raise ValueError("untrusted provider detail")

    with pytest.raises(DispatchRefused, match="dispatch_guard_failed") as error:
        validate_before_dispatch(broken)
    assert isinstance(error.value.__cause__, ValueError)

    def canceled():
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        validate_before_dispatch(canceled)


@pytest.mark.parametrize("reason,kind", [("", DispatchRefusalKind.TERMINAL),
    ("contains spaces", DispatchRefusalKind.TERMINAL), ("safe_reason", "terminal")])
def test_refusal_has_typed_sanitized_reason(reason, kind):
    with pytest.raises(ValueError, match="dispatch_refusal_contract_invalid"):
        DispatchRefused(reason, kind)
