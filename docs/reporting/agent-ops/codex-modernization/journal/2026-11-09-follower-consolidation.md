# Follower consolidation — 2026-11-09

S0 inventory is complete at baseline `50bb2f763`. The canonical
[checkpoint](../checkpoints/2026-11-09-follower-consolidation.md) records scope,
verification and next work. The
[qualification inventory](../../../../followers/05-development/follower-sih-validation-matrix.md)
separates current implementations, historical actual PX4 evidence and remaining
gates. No runtime/default/private configuration, hardware, simulation or release
changed by S0. Baseline checks: 74 passed and schema current.

S1 adds the shared backend catalog/eligibility, command schema 2.2.0, explicit
measurement semantics and separate selection/live readiness. Removed duplicate
compatibility/mount metadata; no algorithm/default/private-profile changes.
Focused gates passed (829, 315 and 54 tests in overlapping commands); fatal lint
and schema pass. The checkpoint records the read-only archived FW replay and
remaining client/owner/VTOL gates. Continue with S2.
