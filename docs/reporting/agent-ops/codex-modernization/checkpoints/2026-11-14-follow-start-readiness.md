# Follow Start readiness repair

## Scope and findings

Offline repair after the operator reported intermittent native FW Start,
misleading QGC conflicts and overly precise speed labels. No simulator restart,
hardware action, deployment, firmware change or public publication is part of
this checkpoint. Public and private gains, limits, geometry and defaults remain
unchanged.

The retained tracking-only probe found nine tracking snapshots with the same
semantic native context: eight refused image/attitude association and one was
ready. Passive source samples arrived about every two seconds (median 1.995 s),
while the qualified camera association allows 50 ms skew. UI reads were driving
source-history progress. Later samples genuinely lost tracking; these remain
valid Start refusals. Retained Dashboard failures lack the exact capture/attitude
pair, so not every observed failure can be attributed to polling.

QGC independently mapped every HTTP 409 to a context-change warning, even when
the server reported an ordinary readiness refusal. Its following properties also
missed target-change notifications. The new regression exposed an early coarse
expiry timer wakeup, leaving a stale QML binding until another status read.

## Repairs

- One connection-owned 50 Hz passive native sampler, sharing the existing RPC
  lock and bounded source history. It yields during acquisition/owned commands,
  rejects obsolete replies, retires invalid evidence, and joins normal cleanup.
- The existing first-pair deadline can bridge a brief missing measurement only
  with unchanged frozen source/target identity and a final fresh measured pair.
  No timestamp renewal, predicted-frame admission or relaxed timing tolerance.
- Canonical native startup reasons survive through the existing action outcome.
  An unresolved teardown takes precedence over an unavailable new Start context.
  Cleanup and authority checks remain mandatory.
- QGC target changes notify following eligibility. Its target expiry uses a
  precise timer with the same six-second policy. Vetted correlated error codes
  replace the misleading universal conflict warning; no action auto-retry.
- Dashboard and QGC speed labels derive display precision from the advertised
  step (0.5 → one decimal, 0.25 → two). Editors and submitted requests keep exact
  values. Dashboard startup failures use concise typed reasons.
- Reconciled stale FW documentation and generated schema description with the
  current bounded Gazebo qualification. Physical camera timing remains gated.

## Operator workflow

| Installation | Current workflow | Next design boundary |
| --- | --- | --- |
| Ordinary MC with image tracker | Choose Stationary, Chase or the purpose-specific MC profile; select target, Start, adjust supported session controls, Stop | Existing catalog governs input and command compatibility |
| Ordinary FW with image tracker | Qualified calibrated image source plus FW Navigation Chase; positive PX4-derived airspeed reference | Physical timing/source qualification remains separate |
| Standard VTOL image training | Choose MC Chase while settled MC, or FW Navigation Chase while settled FW | Declarative installed recipe selecting approved leaf strategies is not implemented yet |
| Gimbal/external Vector | Shared Vector session resolves its declared strategy from fresh phase; mounting/provider conversion stays canonical | Actual source, native runtime and phase qualification remain required |
| Tailsitter | Same VTOL ownership/phase rule; optical visibility and physical-body/quaternion mapping must be qualified | No pitch-based phase guessing or mount swapping during transition |

Transition ends following and requires a new Start after settling. Automatic
recipe selection must not mean automatic resumption. The proposed recipe stores
approved MC/FW profile references in the existing catalog, creates one leaf per
Start, and exposes resolved labels/controls to both clients. It adds no client
follower-name checks or second configuration authority. Unknown phase/input is
unavailable with a specific reason, not guessed from airframe pitch.

## Next visual test (operator start required)

1. Prepare a fresh isolated standard-VTOL run on the ground with renewed hashes;
   verify login/video/status without flickering association prompts.
2. Take off and settle in MC. Select a clearly visible ground feature, Start,
   adjust speed in both clients, and Stop. Confirm observed Hold and responsive UI.
3. Transition using QGC/PX4. Confirm following ended, settled FW phase is reported,
   and no Start was replayed. Choose the current FW image profile explicitly.
4. Select/reacquire a visible feature, Start, adjust airspeed, and Stop. Repeat
   short loss/reselection and cross-client edits; stale requests must refuse with
   an accurate brief reason while Stop stays reachable.
5. Review original captures, matching attitude samples, action outcomes, native
   publication and actual PX4 mode/pose. Unit success is not this acceptance.

## Evidence and outstanding work

Private evidence root:
`reports/sitl/follower-consolidation-20261111/training-vtol-operator-r1/fw-start-review-20261114-r1/`.
Dashboard receipts are under `software-gates-dashboard-startup-display-r1/`;
QGC under `software-gates-s7-qgc-follow-readiness-r1/` beside that run.
Offline gate totals and exact revisions are retained in the final repair receipt.
The QGC full Unit/Integration run initially passed 473/477 suites; its four video
failures reported the host shell's missing existing GStreamer `nice` plugin path.
The video retest uses that installed runtime path, not a source change or test
exclusion. The 269-case client suite passes. Changed-file lint passes; full QGC
lint remains blocked by unrelated stock formatting, executable-bit and other
existing findings. Automatic unrelated lint edits were saved as a patch and
restored, keeping this repair focused.
Final backend unit gate: **7,410 passed, 11 optional GStreamer-introspection
skips**, plus 14 passing subtests. Phase 0: **155 passed**. Dashboard: **57 passed**
and production build/postbuild passed. The committed QGC build passes all five
client/video retest suites; the client suite contains **269 passing cases**.
Schema, critical Python lint, generated API inventory and local documentation
links pass. These sets overlap and must not be added into a single total.
Initial failed test runs remain retained; stale protocol fixtures were renewed,
not silently excluded. Source recovery after power loss is recorded separately
under `qgc-powerloss-recovery-20261114-r1/`.

Remaining: fresh visual runtime acceptance, the declarative VTOL recipe slice,
then source/phase-specific tailsitter and physical-camera checks. No claim of
flawless vision, hardware qualification or complete VTOL composition is made.
