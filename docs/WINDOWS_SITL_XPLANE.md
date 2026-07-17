# Windows And X-Plane SITL Disposition

Status: not currently maintained or accepted as a PixEagle validation path.

The former Windows/WSL/X-Plane procedure used stale PixEagle config syntax,
obsolete scripts, direct remote MAVLink routing, unqualified remote API access,
and manual start/follow commands without the current evidence and safety
contract. Those instructions were removed so operators are not guided through
an unsafe or non-reproducible workflow.

Use the maintained [PX4 SITL Validation Setup](drone-interface/04-infrastructure/sitl-setup.md)
for current L0-L4 validation levels, local-first routing, typed scenario
actions, safety gates, and required evidence artifacts.

PXE-0020 remains open to decide whether X-Plane should return as a maintained
manual L4 evidence workflow. A future Windows/X-Plane guide must, before being
accepted:

- use current PixEagle config schema, launchers, and ports;
- route MAVLink through a documented local-first MavlinkAnywhere topology;
- keep PixEagle backend and MAVLink2REST behind an explicit trusted/authenticated
  boundary;
- use typed guarded action routes and an operator abort procedure;
- capture exact PixEagle/PX4/X-Plane/PX4XPlane/MavlinkAnywhere/MAVLink2REST
  versions and configs;
- produce scenario results, route/profile evidence, PixEagle logs, PX4
  params/ULog/tlog, video/tracker traces, and an acceptance manifest;
- remain manual/operator-gated unless an independently reviewed automation path
  becomes available.

Historical videos may demonstrate earlier project behavior, but they are not
evidence that the current code, routing, safety policy, or validation contract
passes.
