# Follower profile and command schema

`configs/follower_commands.yaml` is the checked-in authority for profile
requirements, command fields/units and dispatch contracts. It is a developer
contract asset, separate from saved operator settings in ConfigService.
`SetpointHandler` validates it before use; current schema version is `2.2.0`.

## Profile declaration

A profile excerpt:

```yaml
follower_profiles:
  mc_velocity_chase:
    family: multicopter
    visibility: basic
    display_name: "MC Velocity Chase"
    description: "Pursuit profile: forward ramp with yaw or sideslip and optional vertical control"
    airframe_phase: multicopter
    control_type: velocity_body_offboard
    required_fields: [vel_body_fwd, vel_body_right, vel_body_down, yawspeed_deg_s]
    ui_category: velocity
    required_tracker_data: [POSITION_2D]
    optional_tracker_data: [BBOX_CONFIDENCE, VELOCITY_AWARE, MULTI_TARGET]
```

Families are `multicopter`, `fixed_wing`, `external` and `vtol`; visibility
is `basic`, `advanced` or `experimental`. These describe presentation and
requirements, not permission to fly. Keep stable profile IDs and explicit
implementation registration. A new YAML profile without an implementation
remains visible but unavailable.

Every required command field belongs to every atomic snapshot. Partial/optional
command snapshots are unsupported. Units, scalar types and any static structural
bounds live in `command_fields`; operational limits remain owned by SafetyManager
or native PX4, not copied into this schema.

## Native phase contracts

The developing Vector path explicitly declares:

```yaml
native_phase_contracts:
  multicopter: velocity_body_offboard
  fixed_wing: fixed_wing_external
  vtol_transition: vtol_transition_external
```

This mapping replaces `native_airframe_phases`; it is not an alias or a
qualification certificate. Native FW uses course/EAS/altitude or height rate;
MC uses its own velocity contract. Do not rename fields to pretend commands
are interchangeable. The current adapter supports only its declared native
contracts; extending one requires an implementation and qualification.

The new end-on-transition policy is still pending. S1 rejects typed API VTOL
Start until transition-preserving release is qualified. Historical native
transition holding does not establish that policy.

## Shared eligibility and clients

`follower_catalog.py` reads this profile plus the tracker's observation
representation and field guarantees. It checks actual samples again at runtime.
There is no independent tracker/follower class compatibility matrix.

`GET /api/v1/integration/following` carries the same catalog for first-party
clients. Selection, implementation/live gating and current Start readiness are
different results. Preserve unavailable saved selections and explain the reason;
do not silently choose another mode or infer capability from an ID prefix.

Profile selection is saved through ConfigService while following is inactive.
A new session resolves it; changing the selected profile does not require a
process reboot. Existing clients retain the `compatible` projection until their
catalog migration. See the [extension guide](../../developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md)
for the exact metadata and validation workflow.

## Command boundary

Followers submit complete nominal `CommandIntent` snapshots; they do not send
MAVSDK/DDS commands directly. Shared continuity and final authorization precede
the command owner. Neither a valid schema nor an accepted nominal intent proves
publication or aircraft response.

The [qualification inventory](../05-development/follower-sih-validation-matrix.md)
records that separate evidence. The [consolidation plan](../05-development/follower-consolidation-plan.md)
tracks phase/strategy migration and removal gates.
