"""The synthetic link matrix preserves a shared budget and control payload."""

import pytest

from tools.qualify_stream_link_matrix import qualify

pytestmark = [pytest.mark.unit, pytest.mark.streaming]


@pytest.mark.asyncio
@pytest.mark.parametrize("rate", [0.5, 1, 2, 5, 10])
async def test_link_matrix_roundtrip(rate):
    result = await qualify(rate, 16 * 1024)
    assert result["connections"] == 2
    assert result["aggregate_budget_shared"]
    assert result["bytes_uplink"] == result["bytes_downlink"] == 16 * 1024 + len(b"status:read")
