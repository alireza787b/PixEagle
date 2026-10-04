"""Deterministic user-space shared-link tests."""

import asyncio
import time

import pytest

from tools.shared_link_relay import SharedLinkRelay

pytestmark = pytest.mark.unit


async def _echo(reader, writer):
    try:
        while data := await reader.read(4096):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_budget_is_aggregate_across_control_and_video_streams():
    upstream = await asyncio.start_server(_echo, "127.0.0.1", 0)
    port = upstream.sockets[0].getsockname()[1]
    payload = b"x" * 20000
    async with SharedLinkRelay("127.0.0.1", port,
                               downlink_bytes_per_second=20000,
                               uplink_bytes_per_second=20000,
                               chunk_bytes=1024) as relay:
        async def round_trip():
            reader, writer = await asyncio.open_connection("127.0.0.1", relay.port)
            writer.write(payload)
            await writer.drain()
            writer.write_eof()
            received = bytearray()
            while data := await reader.read(4096):
                received.extend(data)
            writer.close()
            await writer.wait_closed()
            return bytes(received)

        started = time.monotonic()
        first, second = await asyncio.gather(round_trip(), round_trip())
        elapsed = time.monotonic() - started
    upstream.close()
    await upstream.wait_closed()
    assert first == payload and second == payload
    assert relay.metrics.connections == 2
    assert relay.metrics.bytes_client_to_upstream == len(payload) * 2
    assert relay.metrics.bytes_upstream_to_client == len(payload) * 2
    # The two streams share the 20 kB/s budget. This lower bound tolerates
    # scheduler variance while proving they were not independently shaped.
    assert elapsed >= 0.45


@pytest.mark.asyncio
async def test_latency_is_applied_and_reset_closes_stream():
    upstream = await asyncio.start_server(_echo, "127.0.0.1", 0)
    port = upstream.sockets[0].getsockname()[1]
    async with SharedLinkRelay("127.0.0.1", port, latency_ms=40,
                               chunk_bytes=64, reset_after_bytes=64) as relay:
        reader, writer = await asyncio.open_connection("127.0.0.1", relay.port)
        started = time.monotonic()
        writer.write(b"a" * 128)
        await writer.drain()
        received = await reader.read()
        elapsed = time.monotonic() - started
        writer.close()
        await writer.wait_closed()
    upstream.close()
    await upstream.wait_closed()
    # The reset deliberately tears down both halves after the first bounded
    # uplink chunk; a response is therefore not expected to reach the client.
    assert received == b""
    assert elapsed >= 0.03
    assert relay.metrics.resets >= 1


@pytest.mark.asyncio
async def test_reset_does_not_poison_a_fresh_connection():
    upstream = await asyncio.start_server(_echo, "127.0.0.1", 0)
    port = upstream.sockets[0].getsockname()[1]
    async with SharedLinkRelay("127.0.0.1", port, chunk_bytes=32,
                               reset_after_bytes=32) as relay:
        reader, writer = await asyncio.open_connection("127.0.0.1", relay.port)
        writer.write(b"x" * 64)
        await writer.drain()
        assert await reader.read() == b""
        writer.close()
        await writer.wait_closed()

        relay.reset_after_bytes = None
        reader, writer = await asyncio.open_connection("127.0.0.1", relay.port)
        writer.write(b"fresh-connection")
        await writer.drain()
        writer.write_eof()
        assert await reader.read() == b"fresh-connection"
        writer.close()
        await writer.wait_closed()
        assert relay.metrics.resets >= 1
        assert relay.metrics.connections == 2
    upstream.close()
    await upstream.wait_closed()
