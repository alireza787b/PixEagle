# Validation record

2026-09-17, runtime baseline `463fbbc5acbc107d32cffc6c85cc3670923016ee`.

| Check | Result |
| --- | --- |
| `python3 /tmp/package_gimbal_bench.py` | Passed: 30 completed sessions; no session error records; 1,244 RX deliveries; all recorded TX/RX checksums valid; 117 local frame hashes verified |
| Manifest artifact SHA-256 checks | Passed for every artifact listed in `manifest.json` |
| `ast.parse` for every preserved Python script | Passed; no script execution implied |
| Offline parser/scheduler replay | Completed; existing defects reproduced in `offline-parser-review.json` |
| `bash scripts/check_schema.sh` | Passed: 43 sections, 603 parameters, 9 categories; schema up to date |
| `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py` | Not run: interpreter exited 1 with `No module named pytest` |
| Local Markdown link existence | Passed for evidence README and journal links |
| `git diff --check` | Passed for tracked diff; new artifacts also parsed/hash-checked |
| Final camera query | Session `20260917T051804Z-queries`: tracking disabled; angle query responses received |
| Remaining bench processes | None found after completion |

RX totals include duplicated deliveries: TRC 451, GAC 432, GIA 27, ODZ 30,
OFT 304. They are not independent samples or a packet-loss statistic. All
received checksums being valid does not qualify existing runtime validation:
offline malformed-input tests separately show the runtime accepts bad checksums.

No dashboard tests/build were required for this documentation/evidence-only
slice. No runtime implementation, PX4, SITL, HIL, field, firmware watchdog,
target-loss/reacquisition or cross-platform acceptance was performed.

## PDF-guided follow-up

Updated packaging: 50 completed sessions, 2,672 RX deliveries, no invalid TX/RX
checksums, 240 local image hashes verified. One ai-select session records an
intentional failed freshness precondition; no fuzzy-selection command was sent.
Final session `20260917T072435Z-queries` confirmed TRC00. These remain standalone
bench results. See the PDF-guided checkpoint for unstable manual tracking.


## 2026-09-18 manual integration and exact Qt point check

Packaging now includes 71 completed standalone sessions, 4,451 RX deliveries
(including duplicates), zero invalid recorded TX/RX checksums, and 352 verified
local image hashes. Historical errors remain recorded: the AI freshness
precondition rejected selection, and an attempted home probe found an occupied
UDP port before actuation. Completion of a session is not a success claim.

`manual-integration/` preserves the bounded actual API/browser action records,
4,968-row wire window, source hashes, software versions, final camera status,
probe scripts and test logs. Mapping examples link earlier LOC/OFT bytes to
correct initial centers. The final restored runtime reported tracking disabled,
following false, available/connected true. Room images and vendor PDFs are
excluded from the package.

Resume tests: 178 backend tests and 426 dashboard tests passed; dashboard build,
schema and Python compilation passed. The final camera-status display correction
then passed 27 focused frontend tests and another production build. See the
[checkpoint](../../checkpoints/2026-09-18-gimbal-qt-workflow-review.md) for exact
commands, control outcomes, source analysis, limitations and manufacturer
questions. Target retention remains unqualified; exact Qt point format also lost
the target. No aircraft, SITL, HIL, firmware watchdog or cross-platform hardware
qualification was performed.
