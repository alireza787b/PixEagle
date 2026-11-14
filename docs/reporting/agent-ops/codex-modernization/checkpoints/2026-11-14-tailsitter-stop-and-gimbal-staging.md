# Tailsitter Stop repair and vertical-gimbal staging

## Operator evidence and closure

The operator accepted fixed-nose FW image pursuit but reported failed Stop and
subsequent Start refusal. The run is
`reports/sitl/follower-consolidation-20261111/training-tailsitter-nose-operator-r1`.
All six original token-owned containers, GUI, host relay/frontend and internal
network were closed after saving status and timestamped logs. Physical devices
were untouched. `stop-review-20261114` retains the pre-shutdown snapshots.

Native wire records one acquisition and 353 intent requests. Stop ended the
pursuit socket; subsequent observations retained the original acquisition,
fresh owner confirmation, external navigation state 23, neutral drain and
`release_pending=true`. Repeated Stop attempts did not resolve the receipt.
The backend retained `last_handoff.result=failed`. This is a genuine release
failure, not proof of a QGC transport or camera failure. Local publisher shutdown
must never be described as confirmed Hold.

The original capture does not log each DDS release request/Commander rejection,
so the exact reason the first native release was ineffective is **unconfirmed**.
Do not invent packet-loss or timeout causation from the failed receipt alone.
The code audit independently establishes a liveness defect: release dispatch was
one-shot, and read-only reconciliation could not repair a lost first dispatch.

## Shared repair

The adapter retransmits the identical original request only on progressing
native ownership status, inside the same frozen native deadline and under fresh
exact original Acquired/Releasing ownership. Terminal proof, takeover, rescue,
registration/incarnation change and expiry prevent retries. There is no new
acquisition, deadline renewal, global timeout increase or resumed pursuit.
The same path covers native MC/FW, transition exit, explicit Stop and EOF.
Ordinary MC MAVSDK control remains unchanged.

Native `observe` now records release dispatch count, request source-clock and
expiry, current source-clock and receipt state without exposing ownership tokens.
Backend cleanup failures are also logged rather than only appearing in an
action result. The component runner now exercises App's Stop ordering: immediate
failsafe invalidation/EOF, publisher join, original-acquisition reconciliation.
The current runtime asset and v5 evidence-contract pins are renewed together;
archived evidence is not rewritten.

## Verification boundary

The new native build passes 91 normal and 82 ASan/UBSan contract tests, including
frozen deadline, stale/replacement/takeover rejection and no resumed pursuit.
Build and extracted runtime:
`reports/native-guidance/native-release-repair-20261114-r1`.

The first actual tailsitter cycle confirms native Hold after MC phase exit and
FW Stop. Its full result remains failed: FW altitude-hold error reached 2.200 m
against the unchanged 2.000 m gate. End altitude recovered near the anchor; this
does not erase the exceeded envelope. The initial evidence-source pin mismatch
also prevents that capture from claiming fully attributed publication success.
Both failures remain in `stop-release-cycle-20261114-r1`; do not tune thresholds
merely to recolor the result.

The renewed EOF/application-order cycle (`stop-release-eof-cycle-20261114-r2`)
also confirms both original native Hold receipts, no publication failure and no
publication after Stop. FW's full response remains failed at 2.193 m excursion;
MC received-topic counts do not match its native counter exactly, so per-source
publication attribution stays unknown rather than being inferred. The gates and
final receipt are stored beside it. The deliberately dropped-release cycle
(`stop-release-drop-cycle-20261114-r3/release-proof.json`) confirms Hold after
dropping the first release delivery for each of the MC and FW acquisitions.
Forwarded retries keep the original source clock and expiry. Its full result
still reports the separate altitude-response and publication-attribution gates;
it is not relabelled passed. The fixture is loopback-namespace/token restricted
and introduces no normal runtime relay. Actual operator Stop/restart acceptance
remains required before closing this issue.
No firmware/controller gain, speed/altitude limit, public default or private
gimbal parameter was changed in this repair.

Backend/native integration gates passed 888 tests; the renewed evidence/runner
suites passed 627, and the fault/baseline suites passed 338 (these selections
overlap). Generated schema and critical Python lint passed. No QGC source or
binary changed in this repair.

## Next slices

The [camera mounting guide](../../../../trackers/06-integration/camera-mounting.md)
is the single setting/frame reference for users and agents. The
[training plan](../../../../followers/05-development/ubuntu-training-platform.md#next-checkpoint-vertical-external-gimbal-on-the-tailsitter)
orders shared Stop qualification, protocol parity, a pinned mechanical renderer,
the small aim/lock GUI, deterministic/actual SITL checks and operator acceptance.

Reuse Topotek SIP parsing, independent GAC/TRC freshness, canonical vertical
geometry and the retained FL-30/bench references. The old standalone simulator
is not proof of physical dynamics. Joint travel/rates, stabilization and combined
axis behavior need documented source or measured evidence before claiming an
exact hardware replica. The private October 27 configuration is an archived
comparison, not automatic authority for a newer tailsitter FW overlay.

Hardware reconnection is unnecessary for the initial software slices. Request
it only when an unmeasured physical convention blocks qualification or at the
later operator hardware checkpoint.

## Protocol/GUI slice completed

The existing `tools/gimbal_simulator.py` is now an input stimulus with one UDP
worker, production enums/checksum and independent GAC/TRC cadence. Captured
hardware packets decode through the real provider parser. Incorrect headers,
fabricated OFT angle broadcasts, duplicate enums, automatic package installation
and unmeasured smoothing/pattern motion were removed. The compact GUI uses the
existing installation configuration and shared inverse angle convention; both
mounts were exercised with real Tk layout/worker cleanup. It provides explicit
simulated lock/loss, Center and independent sample-freeze controls.

207 protocol/geometry/provider/documentation tests pass, including actual local
UDP delivery and unchanged forward geometry. See `gimbal-protocol-parity-final-r2.log`
and `gimbal-tk-smoke.log` in the common report directory. Tk was staged locally
from Ubuntu packages for this host check; no system package/service or runtime
configuration was modified. The [short tool guide](../../../../gimbal_simulator.md)
replaces the old misleading full-hardware-emulation instructions.

This slice does not rotate Gazebo or establish a native FW gimbal timing
association. All GUI and flight-test processes remain closed. No private camera
setting was changed.

## Source-time input slice

The operator chose the most practical simulation while the camera is offline.
Use verified SIP/mount conventions and explicitly ideal stabilized pointing;
unmeasured motor response, joint travel and image roll remain unqualified.

The Topotek provider now has an optional private simulator transport. It reuses
the parser, independent GAC/TRC caches and CameraRuntime lifecycle. Original
source stamps and producer receipts survive tracking; queued/paused data cannot
gain fresh timestamps. EOF, malformed/reordered packets and clock/incarnation
changes retire the source. Null `GAZEBO_INPUT` keeps factory UDP behavior.

The renamed shared `gazebo_guidance_alignment.py` binds both image and gimbal
contracts to retained raw PX4 samples. The same readiness/Start gate checks
native FW gimbal timing, mount revision, source owner and selection generation.
Hardware receipt-only input cannot claim simulator source-time qualification.
No synthetic pixels, latest-pose shortcut or fabricated receive-delay bounds
were added.

Initial gates: 160 provider/observation tests and 126 alignment/application tests
pass. Full domain/configuration gates and rendered-camera qualification follow.
Logs: `gimbal-stamped-input-r1.log`, `gimbal-shared-alignment-r2.log` in the common
report directory. These are deterministic/local transport checks, not flight
or rendered-model evidence. The prior FW altitude gate remains open.

## Rendered ideal model and GUI

Added one ideal world-stabilized pointing model, a separate static camera
instrumentation role and a local GUI. Source angles derive from actual Gazebo
camera/aircraft pose feedback; camera pose intents never stand in for measured
motion. World-point lock uses the explicitly entered fixture range. There is
no detector, inferred depth, guessed joint mechanics or aircraft command API.
Bad GUI input preserves current observations/target and reports rejection.

Actual component evidence:
`reports/sitl/follower-consolidation-20261111/gimbal-render-probe-20261114-r1/`.
`pose-and-image-receipt.json` and the before/after PNGs show moved camera pose
and changed rendered pixels. `gui-source-receipt.json` confirms real Tk aim,
finite lock, loss and release through the production SIP parser/CameraRuntime.
`gui-observed-source.jsonl` retains original stamps and receipts. Both owned
containers exited zero and were removed; the aircraft remained on the ground
with no aircraft commands sent.

A camera pose request may be applied despite a missing reply; only observed
pose feedback supplies angles. The Python probe's initial shutdown abort was
resolved by disposing transport explicitly before interpreter shutdown; final
probe and provider exits were zero. Earlier failed probes remain retained.

459 focused renderer/launcher/configuration/Phase 0 checks pass, plus 188
coastal scene/asset/role checks (counts overlap). Logs are
`gimbal-render-software-final-r1.log` and `gimbal-coastal-world-gates-r1.log`.
Native aircraft-following, full QGC operator Stop/restart and the unchanged FW
altitude gate remain separate acceptance items.

The operator additionally requested a richer PixEagle world. A reproducible
coastal scene adds branded signs/road art, cars, balloons, airship and vessels.
It uses pinned locally generated art and static visual props; moving objects,
hydrodynamics and collision qualification are not implied. See
`native/gazebo/README.md`. A fresh ground-start QGC/gimbal stack follows the
remaining software checks and actual scene-render inspection.

The first coastal full-stack launch retired cleanly before QGC opened: startup
uses round-trip YAML numeric subclasses, while the new simulator skew validator
incorrectly required a plain built-in float. It now accepts finite numeric
subclasses while continuing to reject booleans/nonfinite values. The same
round-trip fixture is checked through Config Sync and startup validation;
53 relevant source/profile regressions pass. The failed run remains at
`training-tailsitter-gimbal-coast-operator-r1`; a fresh run is required.
