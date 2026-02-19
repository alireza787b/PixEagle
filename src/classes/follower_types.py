# src/classes/follower_types.py
"""
FollowerType enum — canonical, type-safe identifiers for all follower implementations.

WP9: Created to replace raw string keys throughout the codebase, enabling
IDE completion, typo detection, and exhaustive matching.

Usage:
    from classes.follower_types import FollowerType
    factory.create_follower(FollowerType.MC_VELOCITY_CHASE, px4)
"""

from enum import Enum


class FollowerType(str, Enum):
    """
    Canonical identifiers for all registered follower implementations.

    Naming convention: {platform}_{control}_{behavior}
      - mc_  = Multicopter (velocity or attitude-rate control)
      - fw_  = Fixed-Wing (L1/TECS attitude-rate control)
      - gm_  = Gimbal-guided (runs on MC airframe; gm_ = tracking method, not vehicle)
    """

    # ── Multicopter: Velocity Control ────────────────────────────────────────
    MC_VELOCITY_CHASE    = 'mc_velocity_chase'
    MC_VELOCITY_GROUND   = 'mc_velocity_ground'
    MC_VELOCITY_DISTANCE = 'mc_velocity_distance'
    MC_VELOCITY_POSITION = 'mc_velocity_position'

    # ── Multicopter: Attitude Rate Control ───────────────────────────────────
    MC_ATTITUDE_RATE     = 'mc_attitude_rate'

    # ── Fixed-Wing: Attitude Rate Control (L1/TECS) ──────────────────────────
    FW_ATTITUDE_RATE     = 'fw_attitude_rate'

    # ── Gimbal-Guided: Velocity Control (runs on MC) ─────────────────────────
    GM_VELOCITY_CHASE    = 'gm_velocity_chase'
    GM_VELOCITY_VECTOR   = 'gm_velocity_vector'
