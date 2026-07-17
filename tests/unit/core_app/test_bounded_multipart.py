"""Tests for bounded multipart parsing used by binary upload routes."""

from __future__ import annotations

import asyncio
from tempfile import SpooledTemporaryFile

import pytest
import starlette.formparsers
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException
from starlette.requests import Request

from classes.bounded_multipart import (
    MultipartHeaderLimitExceeded,
    MultipartParseTimeout,
    MultipartSizeLimitExceeded,
    parse_bounded_multipart_form,
)


pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _multipart_request(
    *,
    file_bytes: bytes,
    fields: dict[str, str] | None = None,
    include_content_length: bool = True,
) -> Request:
    boundary = "pixeagle-test-boundary"
    parts: list[bytes] = []
    for name, value in (fields or {}).items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    parts.extend(
        [
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="demo.pt"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode("ascii"),
            file_bytes,
            f"\r\n--{boundary}--\r\n".encode("ascii"),
        ]
    )
    body = b"".join(parts)
    headers = [
        (
            b"content-type",
            f"multipart/form-data; boundary={boundary}".encode("ascii"),
        )
    ]
    if include_content_length:
        headers.append((b"content-length", str(len(body)).encode("ascii")))

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "headers": headers}, receive)


def _raw_request(
    body: bytes,
    *,
    content_type: bytes | None,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    headers = list(extra_headers or [])
    if content_type is not None:
        headers.insert(0, (b"content-type", content_type))

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "headers": headers}, receive)


def _file_part_prefix(boundary: str = "pixeagle-test-boundary") -> bytes:
    return (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="demo.pt"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
        "partial-model"
    ).encode("ascii")


class _StalledRequest:
    def __init__(self, *, started: asyncio.Event, blocker: asyncio.Event) -> None:
        self.headers = Headers(
            {"content-type": "multipart/form-data; boundary=pixeagle-test-boundary"}
        )
        self._started = started
        self._blocker = blocker

    async def stream(self):
        yield _file_part_prefix()
        self._started.set()
        await self._blocker.wait()


async def test_parser_accepts_one_bounded_file_and_fields():
    form = await parse_bounded_multipart_form(
        _multipart_request(
            file_bytes=b"trusted-model",
            fields={"trust_model": "true"},
        ),
        max_file_bytes=64,
    )
    try:
        assert form["trust_model"] == "true"
        assert form["file"].filename == "demo.pt"
        assert await form["file"].read() == b"trusted-model"
    finally:
        await form.close()


async def test_parser_rejects_file_before_it_exceeds_limit():
    with pytest.raises(MultipartSizeLimitExceeded, match="Uploaded file exceeds"):
        await parse_bounded_multipart_form(
            _multipart_request(file_bytes=b"too-large", include_content_length=False),
            max_file_bytes=4,
        )


async def test_parser_rejects_declared_oversize_request_before_streaming():
    with pytest.raises(MultipartSizeLimitExceeded, match="Multipart request exceeds"):
        await parse_bounded_multipart_form(
            _multipart_request(file_bytes=b"small"),
            max_file_bytes=4,
            overhead_bytes=0,
        )


async def test_parser_rejects_invalid_content_length():
    request = _multipart_request(file_bytes=b"small")
    request.scope["headers"] = [
        (name, b"invalid" if name == b"content-length" else value)
        for name, value in request.scope["headers"]
    ]
    if hasattr(request, "_headers"):
        del request._headers

    with pytest.raises(MultiPartException, match="Content-Length"):
        await parse_bounded_multipart_form(request, max_file_bytes=64)


@pytest.mark.parametrize(
    ("content_type", "message"),
    [
        (None, "multipart/form-data with a boundary"),
        (b"application/octet-stream", "must be multipart/form-data"),
        (b"multipart/form-data", "Missing boundary"),
    ],
)
async def test_parser_rejects_missing_or_invalid_content_type(content_type, message):
    request = _raw_request(b"not-a-form", content_type=content_type)

    with pytest.raises(MultiPartException, match=message):
        await parse_bounded_multipart_form(request, max_file_bytes=64)


@pytest.mark.parametrize(
    "boundary",
    [b"ends-with-space ", b"contains@[invalid", b"a" * 71],
)
async def test_parser_rejects_invalid_multipart_boundary(boundary):
    request = _raw_request(
        b"unused",
        content_type=b'multipart/form-data; boundary="' + boundary + b'"',
    )

    with pytest.raises(MultiPartException, match="boundary"):
        await parse_bounded_multipart_form(request, max_file_bytes=64)


async def test_parser_rejects_oversized_request_headers_before_streaming():
    request = _raw_request(
        b"unused",
        content_type=b"multipart/form-data; boundary=test",
        extra_headers=[(b"x-oversized", b"a" * 128)],
    )

    with pytest.raises(MultipartHeaderLimitExceeded, match="Request headers exceed"):
        await parse_bounded_multipart_form(
            request,
            max_file_bytes=64,
            max_request_header_bytes=64,
        )


def _part_with_headers(headers: list[tuple[str, str]]) -> bytes:
    boundary = "part-header-test"
    rendered_headers = "".join(f"{name}: {value}\r\n" for name, value in headers)
    return (
        f"--{boundary}\r\n"
        f"{rendered_headers}\r\n"
        "value\r\n"
        f"--{boundary}--\r\n"
    ).encode("ascii")


@pytest.mark.parametrize(
    ("headers", "limits", "message"),
    [
        (
            [("Content-Disposition", 'form-data; name="field"'), ("X-Extra", "1")],
            {"max_part_headers": 1},
            "more than 1 headers",
        ),
        (
            [("X" * 17, "1"), ("Content-Disposition", 'form-data; name="field"')],
            {"max_part_header_name_bytes": 16},
            "header name exceeds",
        ),
        (
            [("Content-Disposition", 'form-data; name="field"'), ("X-Long", "v" * 17)],
            {"max_part_header_value_bytes": 16},
            "header value exceeds",
        ),
        (
            [("Content-Disposition", 'form-data; name="field"'), ("X-A", "123456")],
            {"max_part_header_bytes": 48},
            "part headers exceed",
        ),
    ],
)
async def test_parser_bounds_each_part_header_resource(headers, limits, message):
    request = _raw_request(
        _part_with_headers(headers),
        content_type=b"multipart/form-data; boundary=part-header-test",
    )

    with pytest.raises(MultipartHeaderLimitExceeded, match=message):
        await parse_bounded_multipart_form(
            request,
            max_file_bytes=64,
            **limits,
        )


async def test_parser_rejects_oversized_text_field():
    boundary = "field-limit-test"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="field"\r\n\r\n'
        "too-long\r\n"
        f"--{boundary}--\r\n"
    ).encode("ascii")
    request = _raw_request(
        body,
        content_type=f"multipart/form-data; boundary={boundary}".encode("ascii"),
    )

    with pytest.raises(MultiPartException, match="Part exceeded maximum size"):
        await parse_bounded_multipart_form(
            request,
            max_file_bytes=64,
            max_field_bytes=4,
        )


async def test_parser_rejects_streamed_body_over_total_limit():
    request = _multipart_request(
        file_bytes=b"small",
        include_content_length=False,
    )

    with pytest.raises(MultipartSizeLimitExceeded, match="Multipart request exceeds"):
        await parse_bounded_multipart_form(
            request,
            max_file_bytes=64,
            overhead_bytes=0,
        )


def _track_spooled_files(monkeypatch) -> list[SpooledTemporaryFile]:
    created: list[SpooledTemporaryFile] = []
    original = starlette.formparsers.SpooledTemporaryFile

    def tracked_spooled_file(*args, **kwargs):
        file = original(*args, **kwargs)
        created.append(file)
        return file

    monkeypatch.setattr(
        starlette.formparsers,
        "SpooledTemporaryFile",
        tracked_spooled_file,
    )
    return created


async def test_parser_timeout_closes_spooled_files(monkeypatch):
    created = _track_spooled_files(monkeypatch)
    started = asyncio.Event()
    blocker = asyncio.Event()
    request = _StalledRequest(started=started, blocker=blocker)

    with pytest.raises(MultipartParseTimeout, match="parsing exceeded"):
        await parse_bounded_multipart_form(
            request,
            max_file_bytes=64,
            parse_timeout_seconds=0.01,
        )

    assert started.is_set()
    assert len(created) == 1
    assert created[0].closed


async def test_parser_cancellation_closes_spooled_files(monkeypatch):
    created = _track_spooled_files(monkeypatch)
    started = asyncio.Event()
    blocker = asyncio.Event()
    request = _StalledRequest(started=started, blocker=blocker)
    task = asyncio.create_task(
        parse_bounded_multipart_form(
            request,
            max_file_bytes=64,
            parse_timeout_seconds=None,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(created) == 1
    assert created[0].closed


async def test_parser_error_after_file_part_closes_spooled_files(monkeypatch):
    created = _track_spooled_files(monkeypatch)
    boundary = "cleanup-on-error"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="demo.pt"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
        "model\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="field"\r\n'
        f"X-Oversized: {'v' * 64}\r\n\r\n"
        "value\r\n"
        f"--{boundary}--\r\n"
    ).encode("ascii")
    request = _raw_request(
        body,
        content_type=f"multipart/form-data; boundary={boundary}".encode("ascii"),
    )

    with pytest.raises(MultipartHeaderLimitExceeded, match="header value exceeds"):
        await parse_bounded_multipart_form(
            request,
            max_file_bytes=64,
            max_part_header_value_bytes=48,
        )

    assert len(created) == 1
    assert created[0].closed
