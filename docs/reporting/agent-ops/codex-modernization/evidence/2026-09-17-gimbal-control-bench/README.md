# Standalone gimbal bench evidence

See the [checkpoint](../../checkpoints/2026-09-17-phase-5-gimbal-control-bench.md)
for conclusions and their limits. This package is protocol investigation
evidence, not a production controller or flight qualification.

`manifest.json` records the runtime commit, session timestamps, exact script
hashes, actions, observed tracking-state transitions, checksums, errors and
artifact hashes. Each session's `events.jsonl` retains exact UDP bytes and
ports or RTSP metadata/frame hashes. Deliveries to multiple listening ports
are counted separately; packet counts are not distinct measurements.

`scripts/<sha256>.py` preserves the exact standalone probe source for a session.
These historical probes are fixed to the original bench host, camera address
and report location. They require an explicit phase; actuation additionally
requires `--execute-standalone-bench`. Do not treat their investigative stop
thread, cleanup or sampled baseline checks as production safety mechanisms.

The recorded commands are `.venv/bin/python /tmp/pixeagle_gimbal_bench.py PHASE`
with `arguments` in the manifest when available. Early sessions before CLI
argument recording used defaults: paired pan/tilt speeds ±5, 150 ms pulses,
center selection, 62×111 point size or 200×200 box size in wire units. The
explicit actuation flag was used for every control session. See the preserved
script and TX bytes rather than inferring behavior from a phase name alone.

`offline-parser-review.json` was produced by `scripts/offline_parser_replay.py`
against the unmodified runtime baseline. It replaces sender methods and sleep
and blocks socket creation during the query/parser tests. Its malformed-checksum
examples were **never transmitted to the camera**. The OFT replay uses the same
UTF-8 replacement decoding as the existing receiver.

Room images remain local in `reports/gimbal-bench/<session>/`. Their hashes
are in the logs and verified while packaging; they are deliberately absent
from Git. Visual conclusions therefore refer to locally inspected artifacts:

- Zoom 1.5×: `20260917T050954Z-observe/tcp-59.png`.
- Zoom returned 1.0×: `20260917T050954Z-observe/tcp-106.png`.
- Point tracking marker: `20260917T051603Z-observe/tcp-149.png`.
- Center box marker: `20260917T051631Z-observe/tcp-151.png`.
- Off-center box marker: `20260917T051729Z-observe/tcp-164.png`.

No source archive, vendor binary, credentials, room image, or PixEagle runtime
configuration is included. Device model, firmware, loss behavior, hardware
watchdog, full ROI bounds and moving-target performance remain unqualified.

Latest: [2026-09-18 Qt workflow and manual integration checkpoint](../../checkpoints/2026-09-18-gimbal-qt-workflow-review.md), including exact Qt click results and `manual-integration/` action/wire evidence.

Follow-on: [Smart selection and restart recovery](../../checkpoints/2026-09-19-gimbal-smart-restart.md). Later operator captures and the read-only ROT02 query are included in the manifest; room images remain local.
