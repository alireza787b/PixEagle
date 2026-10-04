"""Owned loopback TCP impairment relay for camera/control qualification.

The relay is deliberately user-space and loopback-only.  It applies one
aggregate byte budget per direction to all connections, so a video stream and
an API/control stream compete for the same measured budget.  It does not claim
to emulate RF loss, kernel queues, or physical device behaviour.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Self


class _RelayReset(Exception):
    pass


@dataclass
class RelayMetrics:
    bytes_client_to_upstream: int = 0
    bytes_upstream_to_client: int = 0
    chunks_client_to_upstream: int = 0
    chunks_upstream_to_client: int = 0
    connections: int = 0
    resets: int = 0


class _AggregateBudget:
    def __init__(self, rate_bytes_per_second: int | None) -> None:
        self.rate = rate_bytes_per_second
        self._available = float(rate_bytes_per_second or 0)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def reserve(self, amount: int) -> None:
        if not self.rate:
            return
        while True:
            async with self._lock:
                now = time.monotonic()
                self._available = min(float(self.rate), self._available +
                                      (now - self._last) * self.rate)
                self._last = now
                if self._available >= amount:
                    self._available -= amount
                    return
                wait = (amount - self._available) / self.rate
            await asyncio.sleep(min(max(wait, 0.001), 0.1))


class SharedLinkRelay:
    """Forward TCP streams through one shared, deterministic impairment budget."""

    def __init__(self, upstream_host: str, upstream_port: int, *,
                 downlink_bytes_per_second: int | None = None,
                 uplink_bytes_per_second: int | None = None,
                 latency_ms: float = 0, chunk_bytes: int = 4096,
                 reset_after_bytes: int | None = None) -> None:
        if upstream_host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("relay upstream must be loopback")
        if upstream_port < 1 or upstream_port > 65535:
            raise ValueError("invalid upstream port")
        if chunk_bytes < 1 or chunk_bytes > 65536:
            raise ValueError("invalid chunk size")
        if latency_ms < 0:
            raise ValueError("latency cannot be negative")
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.latency = latency_ms / 1000
        self.chunk_bytes = chunk_bytes
        self.reset_after_bytes = reset_after_bytes
        self._downlink = _AggregateBudget(downlink_bytes_per_second)
        self._uplink = _AggregateBudget(uplink_bytes_per_second)
        self.metrics = RelayMetrics()
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set[asyncio.Task] = set()

    @property
    def port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("relay is not running")
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> SharedLinkRelay:
        if self._server is not None:
            raise RuntimeError("relay already running")
        self._server = await asyncio.start_server(self._accept, "127.0.0.1", 0)
        return self

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def __aenter__(self) -> Self:
        return await self.start()

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    async def _accept(self, client_reader: asyncio.StreamReader,
                      client_writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(self._connection(client_reader, client_writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _connection(self, client_reader: asyncio.StreamReader,
                          client_writer: asyncio.StreamWriter) -> None:
        upstream_writer = None
        self.metrics.connections += 1
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(
                self.upstream_host, self.upstream_port)
            tasks = {
                asyncio.create_task(self._forward(client_reader, upstream_writer, self._uplink, True)),
                asyncio.create_task(self._forward(upstream_reader, client_writer, self._downlink, False)),
            }
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            reset = any(not task.cancelled() and task.exception() is not None for task in done)
            if reset:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
            else:
                await asyncio.gather(*pending, return_exceptions=True)
        except (_RelayReset, ConnectionError, asyncio.IncompleteReadError, OSError):
            self.metrics.resets += 1
        finally:
            for writer in (client_writer, upstream_writer):
                if writer is not None:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except OSError:
                        pass

    async def _forward(self, reader: asyncio.StreamReader,
                       writer: asyncio.StreamWriter, budget: _AggregateBudget,
                       client_to_upstream: bool) -> None:
        transferred = 0
        while True:
            payload = await reader.read(self.chunk_bytes)
            if not payload:
                try:
                    writer.write_eof()
                    await writer.drain()
                except (AttributeError, OSError):
                    pass
                return
            reset_after_write = False
            if self.reset_after_bytes is not None:
                remaining = self.reset_after_bytes - transferred
                if remaining <= 0:
                    self.metrics.resets += 1
                    raise _RelayReset
                if len(payload) > remaining:
                    payload = payload[:remaining]
                    reset_after_write = True
            await budget.reserve(len(payload))
            if self.latency:
                await asyncio.sleep(self.latency)
            writer.write(payload)
            await writer.drain()
            transferred += len(payload)
            if client_to_upstream:
                self.metrics.bytes_client_to_upstream += len(payload)
                self.metrics.chunks_client_to_upstream += 1
            else:
                self.metrics.bytes_upstream_to_client += len(payload)
                self.metrics.chunks_upstream_to_client += 1
            if reset_after_write or (self.reset_after_bytes is not None and transferred >= self.reset_after_bytes):
                self.metrics.resets += 1
                raise _RelayReset
