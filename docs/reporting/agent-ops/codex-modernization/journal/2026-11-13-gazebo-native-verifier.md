# Gazebo native simulator verification — 2026-11-13

Extended the existing simulator verifier and isolated host rather than adding a
controller or parallel flight harness. A verified manifest selects the strict
SIH/Gazebo builder once. Gazebo binds the runtime image, actual PX4 binary,
resource tree, scene, topics and identity parameters read from the verified
packaged 4018 airframe. Unknown or ambiguous declarations and an empty process
transport partition are rejected. Small shared container helpers check original
IDs and ownership tokens before and after stopping. Native
source contracts and pre-transition checks retain that authority. SIH composite
ROS runtime and default compatibility behavior remain supported.

The canonical execution APIs use `simulation_build_manifest` and
`--simulation-build-manifest`; historical scripts/evidence and the separate SIH
gallery are unchanged. The builder, allocator, guidance gains, public/private
configuration and sensorless stable-window predicate were not modified.

Validation: 722 focused simulator/native ownership/host tests passed, along with
source syntax, selected flake8 error checks and retained disarmed
scene/topic/parameter replay. The replay reused recorded probe output and is
not a new running-container verification. A final model-binding correction keeps
explicit caller model constraints: conflicting Gazebo selections refuse before
staging, and omitted selections retain the SIH default or manifest-derived
Gazebo model. Its focused host/verifier/MC regression rerun passed 340 tests.
Review evidence is under
`reports/sitl/follower-consolidation-20261111/software-gates-s7-gazebo-native-verifier-r1`. No simulator launch, owner
acquisition, arm, transition, firmware compilation or hardware operation in this
slice. First native-only Gazebo baseline, transition response, sensorless-from-
start and follower qualification remain separate gates.

Root independently renews 608 verifier, native ownership, stable-flight and
shared-host checks on the integrated source. A missing Gazebo manifest is also
rejected before model derivation or staging. Fatal lint and diff checks pass.
