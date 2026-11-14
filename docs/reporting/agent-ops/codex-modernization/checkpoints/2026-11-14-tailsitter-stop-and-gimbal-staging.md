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
