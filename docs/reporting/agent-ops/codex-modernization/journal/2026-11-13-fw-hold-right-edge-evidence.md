# FW native Hold endpoint evidence contract

The original no-pitot V1 capture was nonpassing solely because two recorded FW
setpoint rows shared the correlated native Hold epoch. Its original result and
raw files remain unchanged. A new source review checks every compiled adapter
normal, startup, transition and neutral output form, SDK materialization,
deserializer behavior and native FMM output. The recorded pair is disjoint from
all adapter output forms and matches native Hold.

The auditor now reports that exact, source-bound FW right-edge case separately.
It requires one row per topic and unique same-epoch native Hold/inactive-owner/
auto-position witnesses. It neither counts boundary rows as external receipts
nor changes the half-open authority interval, 100 ms cadence, pose/height gates
or independent Stop fences. Mixed/external/malformed/missing/duplicate or
uncorrelated endpoints remain UNKNOWN; interior native shapes and MC edges are
not exempt. Complete delivery, overwritten writes and within-tick ordering
remain unproven.

The source proof and implementation review live under the respective
`software-gates-s7-fw-hold-right-edge-source-review-r1` and
`software-gates-s7-fw-hold-right-edge-auditor-r1` report directories. Contract
regressions include the formerly refused native endpoint, all refusal classes,
interior source contamination and an endpoint that cannot fill a >100 ms gap.
Actual replay uses the normal source/artifact validators and is saved separately.
No runtime, native build, controller, configuration, safety default or hardware
change is included. Runtime-helper/assets pins remain unchanged; the single
source-review pin advances to this new proof.
