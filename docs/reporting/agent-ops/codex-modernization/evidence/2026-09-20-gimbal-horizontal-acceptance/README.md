# Partial horizontal camera acceptance evidence

These records cover 2026-09-20 03:01:45–03:08:38 UTC. They were collected
before the operator paused hardware testing and archived afterward without
contacting the camera. See the
[checkpoint](../../checkpoints/2026-09-20-gimbal-horizontal-acceptance.md)
for findings and outstanding acceptance.

| Artifact | Meaning |
| --- | --- |
| `browser-hold-events.json`, `browser_hold.cjs` | Actual live browser Fine pan holds, release and Stop requests/results |
| `hold-image-motion.json` | Relative image displacement for the two holds; includes any base motion |
| Six timestamped axis JSONL files | Individual pulse parameters, typed telemetry, action results and cleanup |
| `axis-image-motion.json` | Selected native image changes around wire commands; includes three additional unattributed tilt pulses |
| `axis_pulse.py` | Current harness, including a pose guard added **after** these probes; this exact revision was not executed |
| `browser-box-events.json` | Protocol locator timeout before selection; Cancel and Stop cleanup |
| `browser_box.cjs` | Current harness with an unexecuted locator correction; not the exact failed revision |
| `read_orientation.py`, orientation JSONL files | Read-only image-rotation query and raw `ROT02` replies; `accepted:false` means the tracker did not consume this diagnostic packet |
| `paused-status.json` | Disconnected final snapshot, following off, tracking unknown |
| `wire-window.jsonl` | Raw camera TX/RX subset bounded to the session, including normal backend polling and commands from any client |
| Two timestamped capture folders | Original passive capture event logs and archived capture script |
| `private-frame-hashes.json` | SHA-256/path inventory of private JPEGs; no image bytes are published here |
| `manifest.json` | SHA-256 and size of archived evidence artifacts |

The existing software provenance is recorded in
[movement-controls evidence](../2026-09-20-gimbal-movement-controls/README.md).
The runtime used its isolated bench configuration, following off, command
preview/circuit breaker enabled, and MAVLink disabled. Camera firmware previously
reported `1.6.26.R.D`; this session did not independently re-query firmware.

Executed probe invocations can be reconstructed from each JSONL `start` record:

```text
.venv/bin/python reports/gimbal-acceptance-20260920/axis_pulse.py pan 1
.venv/bin/python reports/gimbal-acceptance-20260920/axis_pulse.py pan -1 --speed 10 --duration 250
.venv/bin/python reports/gimbal-acceptance-20260920/axis_pulse.py tilt 1
.venv/bin/python reports/gimbal-acceptance-20260920/axis_pulse.py tilt -1
.venv/bin/python reports/gimbal-acceptance-20260920/axis_pulse.py roll 1
.venv/bin/python reports/gimbal-acceptance-20260920/axis_pulse.py roll -1
node reports/gimbal-acceptance-20260920/browser_hold.cjs
node reports/gimbal-acceptance-20260920/browser_box.cjs
```

These are historical invocations, not instructions to run the revised harnesses.
The scripts contain local paths and actual camera mutations. The archived hold
test used Chrome 150.0.7871.128 at desktop 1280×1000. Captures record Python
3.12.3, 180-second durations and 5 saved frames/s; their source images were
1920×1080 and saved JPEGs 960×540. Image measurements used feature tracking and
robust partial-affine fitting; the original inline analysis program was not
persisted, so these JSON results are derived observations rather than a fully
replayable analysis fixture. Private frame hashes preserve their local inputs.

The bounds guard and browser locator edit are intentionally identified instead
of reconstructing an unrecorded earlier source revision. No new source hashes
are asserted for the hardware runtime after the UI work began.
