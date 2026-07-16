"""Bounded multipart parsing for authenticated binary-ingestion routes."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import suppress
from typing import Any, Optional

from starlette.datastructures import FormData, Headers
from starlette.formparsers import (
    MultiPartException,
    MultiPartParser,
    parse_options_header,
)


DEFAULT_MULTIPART_OVERHEAD_BYTES = 64 * 1024
DEFAULT_MAX_REQUEST_HEADER_BYTES = 16 * 1024
DEFAULT_MAX_PART_HEADERS = 16
DEFAULT_MAX_PART_HEADER_NAME_BYTES = 256
DEFAULT_MAX_PART_HEADER_VALUE_BYTES = 8 * 1024
DEFAULT_MAX_PART_HEADER_BYTES = 16 * 1024
DEFAULT_MAX_BOUNDARY_BYTES = 70
DEFAULT_PARSE_TIMEOUT_SECONDS = 120.0

_VALID_BOUNDARY = re.compile(
    rb"[0-9A-Za-z'()+_,./:=? -]*[0-9A-Za-z'()+_,./:=?-]\Z"
)


class MultipartSizeLimitExceeded(MultiPartException):
    """Raised before a multipart body can exceed its configured byte budget."""


class MultipartHeaderLimitExceeded(MultiPartException):
    """Raised before request or part headers exceed their configured budget."""


class MultipartParseTimeout(MultiPartException):
    """Raised when a multipart body is not parsed within its wall-clock budget."""


class BoundedMultiPartParser(MultiPartParser):
    """Starlette multipart parser that also limits file parts.

    Starlette's ``max_part_size`` currently limits text fields only. Binary
    file parts need an explicit independent counter before they are written to
    the parser's spooled temporary file.
    """

    def __init__(
        self,
        headers: Headers,
        stream: AsyncGenerator[bytes, None],
        *,
        max_file_bytes: int,
        max_files: int = 1,
        max_fields: int = 4,
        max_field_bytes: int = 4096,
        max_part_headers: int = DEFAULT_MAX_PART_HEADERS,
        max_part_header_name_bytes: int = DEFAULT_MAX_PART_HEADER_NAME_BYTES,
        max_part_header_value_bytes: int = DEFAULT_MAX_PART_HEADER_VALUE_BYTES,
        max_part_header_bytes: int = DEFAULT_MAX_PART_HEADER_BYTES,
    ) -> None:
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        if min(
            max_files,
            max_fields,
            max_field_bytes,
            max_part_headers,
            max_part_header_name_bytes,
            max_part_header_value_bytes,
            max_part_header_bytes,
        ) <= 0:
            raise ValueError("Multipart count and byte limits must be positive")
        super().__init__(
            headers,
            stream,
            max_files=max_files,
            max_fields=max_fields,
            max_part_size=max_field_bytes,
        )
        self.max_file_bytes = max_file_bytes
        self.max_part_headers = max_part_headers
        self.max_part_header_name_bytes = max_part_header_name_bytes
        self.max_part_header_value_bytes = max_part_header_value_bytes
        self.max_part_header_bytes = max_part_header_bytes
        self._current_file_bytes = 0
        self._current_header_count = 0
        self._current_header_bytes = 0

    def on_part_begin(self) -> None:
        super().on_part_begin()
        self._current_file_bytes = 0
        self._current_header_count = 0
        self._current_header_bytes = 0

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self._current_file_bytes += end - start
            if self._current_file_bytes > self.max_file_bytes:
                raise MultipartSizeLimitExceeded(
                    f"Uploaded file exceeds the {self.max_file_bytes} byte safety limit"
                )
        super().on_part_data(data, start, end)

    def _account_header_bytes(self, byte_count: int) -> None:
        self._current_header_bytes += byte_count
        if self._current_header_bytes > self.max_part_header_bytes:
            raise MultipartHeaderLimitExceeded(
                "Multipart part headers exceed the "
                f"{self.max_part_header_bytes} byte safety limit"
            )

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        byte_count = end - start
        if len(self._current_partial_header_name) + byte_count > (
            self.max_part_header_name_bytes
        ):
            raise MultipartHeaderLimitExceeded(
                "Multipart part header name exceeds the "
                f"{self.max_part_header_name_bytes} byte safety limit"
            )
        self._account_header_bytes(byte_count)
        super().on_header_field(data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        byte_count = end - start
        if len(self._current_partial_header_value) + byte_count > (
            self.max_part_header_value_bytes
        ):
            raise MultipartHeaderLimitExceeded(
                "Multipart part header value exceeds the "
                f"{self.max_part_header_value_bytes} byte safety limit"
            )
        self._account_header_bytes(byte_count)
        super().on_header_value(data, start, end)

    def on_header_end(self) -> None:
        self._current_header_count += 1
        if self._current_header_count > self.max_part_headers:
            raise MultipartHeaderLimitExceeded(
                "Multipart part has more than "
                f"{self.max_part_headers} headers"
            )
        super().on_header_end()

    def close_files(self) -> None:
        """Close every spool file created before parsing completed."""
        for file in self._files_to_close_on_error:
            with suppress(Exception):
                file.close()
        self._file_parts_to_write.clear()
        self._file_parts_to_finish.clear()


async def _bounded_stream(
    stream: AsyncIterable[bytes],
    *,
    max_request_bytes: int,
) -> AsyncGenerator[bytes, None]:
    consumed = 0
    async for chunk in stream:
        consumed += len(chunk)
        if consumed > max_request_bytes:
            raise MultipartSizeLimitExceeded(
                f"Multipart request exceeds the {max_request_bytes} byte safety limit"
            )
        yield chunk


async def parse_bounded_multipart_form(
    request: Any,
    *,
    max_file_bytes: int,
    max_files: int = 1,
    max_fields: int = 4,
    max_field_bytes: int = 4096,
    overhead_bytes: int = DEFAULT_MULTIPART_OVERHEAD_BYTES,
    max_request_header_bytes: int = DEFAULT_MAX_REQUEST_HEADER_BYTES,
    max_part_headers: int = DEFAULT_MAX_PART_HEADERS,
    max_part_header_name_bytes: int = DEFAULT_MAX_PART_HEADER_NAME_BYTES,
    max_part_header_value_bytes: int = DEFAULT_MAX_PART_HEADER_VALUE_BYTES,
    max_part_header_bytes: int = DEFAULT_MAX_PART_HEADER_BYTES,
    max_boundary_bytes: int = DEFAULT_MAX_BOUNDARY_BYTES,
    parse_timeout_seconds: Optional[float] = DEFAULT_PARSE_TIMEOUT_SECONDS,
) -> FormData:
    """Parse multipart form data within explicit time and resource budgets."""
    if max_file_bytes <= 0 or overhead_bytes < 0 or max_request_header_bytes <= 0:
        raise ValueError("Multipart byte limits are invalid")
    if max_boundary_bytes <= 0:
        raise ValueError("max_boundary_bytes must be positive")
    if parse_timeout_seconds is not None and parse_timeout_seconds <= 0:
        raise ValueError("parse_timeout_seconds must be positive or None")

    headers = request.headers
    request_header_bytes = sum(
        len(name) + len(value) + 4 for name, value in headers.raw
    )
    if request_header_bytes > max_request_header_bytes:
        raise MultipartHeaderLimitExceeded(
            "Request headers exceed the "
            f"{max_request_header_bytes} byte safety limit"
        )

    content_type = headers.get("content-type")
    if not content_type:
        raise MultiPartException(
            "Content-Type must be multipart/form-data with a boundary"
        )
    media_type, options = parse_options_header(content_type)
    if media_type.lower() != b"multipart/form-data":
        raise MultiPartException("Content-Type must be multipart/form-data")
    boundary = options.get(b"boundary")
    if not boundary:
        raise MultiPartException("Missing boundary in multipart Content-Type")
    if len(boundary) > max_boundary_bytes:
        raise MultipartHeaderLimitExceeded(
            "Multipart boundary exceeds the "
            f"{max_boundary_bytes} byte safety limit"
        )
    if _VALID_BOUNDARY.fullmatch(boundary) is None:
        raise MultiPartException("Multipart boundary contains invalid characters")

    max_request_bytes = max_file_bytes + overhead_bytes
    content_length = headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except (TypeError, ValueError) as exc:
            raise MultiPartException("Content-Length must be a non-negative integer") from exc
        if declared_length < 0:
            raise MultiPartException("Content-Length must be a non-negative integer")
        if declared_length > max_request_bytes:
            raise MultipartSizeLimitExceeded(
                f"Multipart request exceeds the {max_request_bytes} byte safety limit"
            )

    bounded_stream = _bounded_stream(
        request.stream(),
        max_request_bytes=max_request_bytes,
    )
    parser = BoundedMultiPartParser(
        headers,
        bounded_stream,
        max_file_bytes=max_file_bytes,
        max_files=max_files,
        max_fields=max_fields,
        max_field_bytes=max_field_bytes,
        max_part_headers=max_part_headers,
        max_part_header_name_bytes=max_part_header_name_bytes,
        max_part_header_value_bytes=max_part_header_value_bytes,
        max_part_header_bytes=max_part_header_bytes,
    )
    try:
        if parse_timeout_seconds is None:
            return await parser.parse()
        return await asyncio.wait_for(
            parser.parse(),
            timeout=parse_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        parser.close_files()
        raise MultipartParseTimeout(
            "Multipart parsing exceeded the "
            f"{parse_timeout_seconds:g} second safety limit"
        ) from exc
    except BaseException:
        parser.close_files()
        raise
