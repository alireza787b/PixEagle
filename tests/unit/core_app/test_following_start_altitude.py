"""Offboard startup must reject altitude outside the configured follower envelope."""

from types import SimpleNamespace

import pytest

from classes.following_readiness import evaluate_following_start_altitude


@pytest.mark.parametrize(
    "altitude,ready,code",
    [
        (None, False, "following_altitude_unavailable"),
        (float("nan"), False, "following_altitude_unavailable"),
        (3.0, False, "following_altitude_below_start_margin"),
        (4.99, False, "following_altitude_below_start_margin"),
        (5.0, True, None),
        (117.99, True, None),
        (118.01, False, "following_altitude_above_start_margin"),
    ],
)
def test_start_margin_uses_configured_safety_buffer(altitude, ready, code):
    limits = SimpleNamespace(safety_enabled=True, min_altitude=3.0,
                             max_altitude=120.0, warning_buffer=2.0)
    app = SimpleNamespace(px4_interface=SimpleNamespace(current_altitude=altitude))
    result = evaluate_following_start_altitude(app, limits=limits)
    assert result["ready"] is ready
    assert result.get("code") == code


def test_disabled_altitude_safety_does_not_require_a_height():
    limits = SimpleNamespace(safety_enabled=False)
    assert evaluate_following_start_altitude(SimpleNamespace(), limits=limits) == {"ready": True}
