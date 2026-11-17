# MC camera and session-speed checkpoint

**Open: following acceptance is blocked by a reproduced capture/readiness race.**
This is the first MC operator checkpoint in the
[training workflow](../../../../followers/05-development/ubuntu-training-platform.md),
not FW/VTOL or hardware qualification.

Implemented in isolated development branches:

- MC Velocity Chase uses Vector's existing session-speed capability/action and
  owned velocity envelope. Its image-error guidance remains independent.
- Dashboard and QGC display the backend's optional control description. No
  follower-name inference or extra saved speed setting is added to either UI.
- The normal supervised application, declared Gazebo camera, pure-MC PX4 and
  private QGC settings run together. The existing Dashboard production server
  and a loopback API relay keep flight UDP inside the owned simulation network.
- Actual PX4 takeoff and the canonical seven-sample stable Hold gate passed at
  6 m. Camera tracking and both UIs work; Start exposed a shared source defect.

The reproduced defects are ordinary duplicate camera polls being treated as
source loss, and readiness reading partially updated tracker state. Repair must
process each actual capture once and preserve original observation timestamps,
source/target identities and existing expiry guards. External angle guidance
must continue independently of video. The known completed-failure response also
needs correct QGC labeling; genuine missing or ambiguous outcomes remain unknown.

Before that repair: 7,120 unit, 196 integration and 155 Phase 0 tests passed.
Schema passed using the project environment after retaining an initial host-PATH
dependency failure. Client-focused tests/builds passed; full QGC Unit retains
two existing filesystem-watcher failures, and full lint retains baseline issues.
Renew relevant gates after the capture repair; these counts do not qualify it.

Evidence is under
`reports/sitl/follower-consolidation-20261111/training-mc-operator-r1` and adjacent
`software-gates-training-*` packets. Retain failed attempts and actual PX4 pose.
For the next retry, update/restart only PixEagle; preserve the current PX4 and
Gazebo instance. No hardware, public defaults, private field profile, push,
release or firmware flashing changed in this checkpoint.
