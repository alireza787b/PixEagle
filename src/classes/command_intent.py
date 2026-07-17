"""Typed follower command intent passed toward the PX4 command boundary."""

from dataclasses import dataclass, field
from datetime import datetime
import time
from typing import Dict, Optional


@dataclass(frozen=True)
class CommandIntent:
    """
    Immutable, validated command snapshot produced by follower logic.

    This is the boundary between follower math and command publication. It does
    not send MAVSDK commands by itself; it records the full field set that was
    atomically accepted by the active setpoint handler.
    """

    profile_name: str
    control_type: str
    fields: Dict[str, float]
    source: str
    reason: Optional[str] = None
    created_at_monotonic_s: float = field(default_factory=time.monotonic)
    created_at_utc: str = field(default_factory=lambda: datetime.utcnow().isoformat())
