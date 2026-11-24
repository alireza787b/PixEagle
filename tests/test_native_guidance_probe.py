import io
import json

import pytest

from classes.aircraft_state import AircraftBinding
from classes.native_guidance import NativeCapabilities
from tools.native_guidance_probe import record_observations


class ReadOnlyClient:
    def __init__(self):
        self.operations = []

    async def connect(self):
        self.operations.append("hello")
        return NativeCapabilities("runtime", "firmware", 2, True, False, False)

    async def bind(self, binding):
        self.operations.append("bind")

    async def observe(self):
        self.operations.append("observe")
        return {"fresh": False, "vehicle_pose": None, "source_health": {"position_fresh": False}}

    async def close(self):
        self.operations.append("close")


@pytest.mark.asyncio
async def test_probe_is_read_only_and_preserves_unknown_pose():
    client, output = ReadOnlyClient(), io.StringIO()
    ticks = iter([0., .1, .2, 2.])
    counts = await record_observations(client, AircraftBinding("uid", "connection", 1), output,
                                      duration_s=1., interval_s=0, clock=lambda: next(ticks))
    rows = [json.loads(line) for line in output.getvalue().splitlines()]
    assert client.operations == ["hello", "bind", "observe", "close"]
    assert rows[0]["control_actions_permitted"] is False
    assert rows[1]["value"]["vehicle_pose"] is None
    assert rows[1]["value"]["fresh"] is False
    assert counts == {"observations": 1, "fresh": 0, "pose": 0}
