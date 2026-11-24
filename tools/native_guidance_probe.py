#!/usr/bin/env python3
"""Record native PX4 observations without acquiring command authority.

This tool only sends hello, bind and observe over the private adapter socket.
It never arms, selects a mode, starts following or requests a transition.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from classes.aircraft_state import AircraftBinding  # noqa: E402
from classes.native_guidance import NativeGuidanceClient  # noqa: E402


async def record_observations(client, binding: AircraftBinding, output, *, duration_s: float,
                              interval_s: float = .05, clock=time.monotonic) -> dict:
    if not 0 < duration_s <= 3600 or not 0 <= interval_s <= 10:
        raise ValueError("Invalid observation duration or interval")
    counts = {"observations": 0, "fresh": 0, "pose": 0}
    try:
        capabilities = await client.connect()
        await client.bind(binding)
        output.write(json.dumps({"kind": "runtime", "capabilities": asdict(capabilities),
                                 "binding": asdict(binding), "control_actions_permitted": False}) + "\n")
        deadline = clock() + duration_s
        while clock() < deadline:
            observation = await client.observe()
            counts["observations"] += 1
            counts["fresh"] += observation.get("fresh") is True
            counts["pose"] += observation.get("vehicle_pose") is not None
            output.write(json.dumps({"kind": "observation", "received_at_monotonic_s": clock(),
                                     "value": observation}, allow_nan=False) + "\n")
            output.flush()
            await asyncio.sleep(interval_s)
    finally:
        await client.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--aircraft-uid", required=True, help="UID independently verified by the aircraft connection")
    parser.add_argument("--connection-generation", required=True)
    parser.add_argument("--telemetry-generation", type=int, required=True)
    parser.add_argument("--duration-s", type=float, default=10.)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binding = AircraftBinding(args.aircraft_uid, args.connection_generation, args.telemetry_generation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Do not silently overwrite earlier evidence.
    with args.output.open("x") as output:
        counts = asyncio.run(record_observations(NativeGuidanceClient(args.socket), binding, output,
                                                 duration_s=args.duration_s))
    print(json.dumps(counts))
    if counts["fresh"] == 0 or counts["pose"] == 0:
        raise SystemExit("No complete fresh native observation: inspect source_health in the trace.")


if __name__ == "__main__":
    main()
