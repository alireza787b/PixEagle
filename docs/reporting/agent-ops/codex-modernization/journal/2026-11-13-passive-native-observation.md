# Passive native observation candidate

The unpublished candidate reuses a connection-owned native client during
authenticated following-status polling. Read-only preparation runs on the
existing flight loop under the follower lifecycle lock; an active publisher
retains sole observation ownership. Cached readiness reads the actual native
phase. Start prepares before aircraft admission and reuses capabilities when
building its owner, avoiding duplicate discovery.

Focused synthetic I/O regressions cover reuse counts, active-owner exclusion,
queued polls, errors, cancellation, runtime replacement and obsolete replies
across connection/telemetry/identity changes. No simulator, firmware build,
QGroundControl or hardware was run for this slice. The VTOL admission constant,
public defaults, native adapter and firmware remain unchanged.

The initial HTTP Start guard still lacks a native phase/intention pin across
pre-binding work. This remains a required negative case before VTOL promotion;
the existing binding rejects changed phases before pursuit. Actual same-App
qualification also needs its verified MAVSDK/MAVLink route and isolated default
native socket. This candidate adds no test permission flag or eligibility
override.

The source, focused validation and remaining limits are frozen under
`reports/sitl/follower-consolidation-20261111/software-gates-s7-passive-native-observation-r1`.
