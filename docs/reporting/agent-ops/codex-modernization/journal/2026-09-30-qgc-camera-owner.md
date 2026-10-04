# QGC camera ownership implementation

Read backend AGENTS, architecture/API modernization guidance and camera provider
reference before edits. Inspection found camera controls reachable only through
the active GimbalTracker and a dashboard assumption equating camera controls
with camera-owned target selection. Reused the existing provider and protocol
adapter under one AppController camera owner, then separated the dashboard
engine state. Preserved existing config keys and public route paths.

Mock verification caught and corrected a missing audit status argument that unit
mocks did not detect. The real-auth HTTP fixture now performs a synthetic native
movement through the same action executor and audit owner as production.

Joystick safety review later found a discarded final pulse Stop transmission
result. Propagated that failure to action clients and added four transport-failure
regressions with explicit Stop retry. The camera, route, config and inventory
gate passed 264 tests; schema, generated inventory and syntax checks also passed.
This is simulated transport evidence, not physical stopping confirmation.

See [checkpoint](../checkpoints/2026-09-30-qgc-camera-owner.md) and
[native camera contract](../../../../apis/native-camera-controls.md).
