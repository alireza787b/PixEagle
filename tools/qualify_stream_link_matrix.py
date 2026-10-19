#!/usr/bin/env python3
"""Measure the owned loopback relay at the documented synthetic link rates.

This intentionally uses TCP loopback and bounded payloads. It qualifies pacing,
aggregate budget sharing and recovery in software; it is not radio or camera
latency evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

try:
    from tools.shared_link_relay import SharedLinkRelay
except ModuleNotFoundError:
    from shared_link_relay import SharedLinkRelay


async def _echo(reader, writer):
    try:
        while chunk := await reader.read(65536):
            writer.write(chunk)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def _roundtrip(port: int, payload: bytes) -> float:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    started = time.monotonic()
    writer.write(payload)
    await writer.drain()
    writer.write_eof()
    received = bytearray()
    while chunk := await reader.read(65536):
        received.extend(chunk)
    writer.close()
    await writer.wait_closed()
    if bytes(received) != payload:
        raise RuntimeError("loopback relay changed payload")
    return time.monotonic() - started


async def qualify(rate_mbps: float, video_bytes: int) -> dict:
    upstream = await asyncio.start_server(_echo, "127.0.0.1", 0)
    upstream_port = upstream.sockets[0].getsockname()[1]
    bytes_per_second = int(rate_mbps * 1_000_000 / 8)
    control = b"status:read"
    video = b"v" * video_bytes
    async with SharedLinkRelay("127.0.0.1", upstream_port,
                               downlink_bytes_per_second=bytes_per_second,
                               uplink_bytes_per_second=bytes_per_second,
                               chunk_bytes=4096) as relay:
        started = time.monotonic()
        control_elapsed, video_elapsed = await asyncio.gather(
            _roundtrip(relay.port, control), _roundtrip(relay.port, video))
        elapsed = time.monotonic() - started
        metrics = relay.metrics
    upstream.close()
    await upstream.wait_closed()
    return {"rate_mbps": rate_mbps, "video_bytes": video_bytes,
            "elapsed_seconds": round(elapsed, 4),
            "control_elapsed_seconds": round(control_elapsed, 4),
            "video_elapsed_seconds": round(video_elapsed, 4),
            "connections": metrics.connections,
            "bytes_uplink": metrics.bytes_client_to_upstream,
            "bytes_downlink": metrics.bytes_upstream_to_client,
            "aggregate_budget_shared": metrics.bytes_client_to_upstream == len(control) + len(video)}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rates", nargs="+", type=float, default=[0.5, 1, 2, 5, 10])
    parser.add_argument("--video-bytes", type=int, default=256 * 1024)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if any(rate <= 0 for rate in args.rates) or args.video_bytes <= 0:
        parser.error("rates and video-bytes must be positive")
    results = [await qualify(rate, args.video_bytes) for rate in args.rates]
    report = {"scope": "loopback_tcp_aggregate_budget", "results": results,
              "limitations": ["synthetic TCP loopback", "no radio/camera/QGC physical latency",
                              "no kernel loss/jitter or RF behavior"]}
    serialized = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
