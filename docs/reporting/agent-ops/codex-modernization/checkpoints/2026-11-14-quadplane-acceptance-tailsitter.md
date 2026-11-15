# Quadplane acceptance and fixed-nose tailsitter checkpoint

The operator accepted the standard-quadplane run on 14 November 2026. The owned
stack was then closed through the launcher's normal cleanup; all six containers
and its internal network were removed. Unrelated containers were untouched.

## Accepted evidence

Run: `reports/sitl/follower-consolidation-20261111/training-vtol-operator-r2`.
Original backend/PX4/QGC logs, native wire, command/publication traces, final
status and the derived review are retained under that run's `acceptance-review`.

| Session | Profile | Successful submissions | Speed revisions |
| --- | --- | ---: | --- |
| 1 | MC Chase | 205 | 1–8 |
| 2 | FW Navigation Chase | 213 | 1–5 |
| 3 | FW Navigation Chase | 263 | 1–14 |

All 681 attempted command submissions succeeded; no native error reply, backend
traceback or capture-read failure was found. The final following state was
inactive, with operator Stop and confirmed Hold. The operator subsequently
landed/disarmed. These are submission and workflow observations, not a new claim
that every requested command was achieved by a real aircraft. Genuine CSRT
appearance-loss events after Stop remain recorded. Two passive rediscovery
warnings followed normal Stop; neither establishes an active follow interruption.

Backend source: `e1f86b03017e8be49089571fcd42c7e75adf9ba1`.
QGC: `ef52e369e2318d2d0a47cbbb611cb6edb77ec388`; binary SHA-256
`82b0a04d8a73412c09589910f4339a7c471768a3a86c56f438daf07a44c42288`.
Firmware ELF: `5f42a1abb96894bdc0a429db06edced09dda7a8116c53301297bcbcab3181c37`.
Earlier failed runs and the [readiness repair](2026-11-14-follow-start-readiness.md)
remain separate.

## Next test and scope

The fixed-nose tailsitter scenario reuses that exact firmware build, native
adapter, camera provider and QGC binary. It adds a pinned camera wrapper and
general fixed-mount rotation support. FW Navigation Chase is preselected through
the generic launcher option; actual phase and measurement admission remain
authoritative. No firmware/controller tuning, public defaults or private gimbal
profile change belongs to this slice.

The focused suite passed 500 tests covering mount-axis signs, quaternion
composition, ordered PX4 airframe defaults, resource closure, profile preparation
and FW image guidance. The two Phase 0 suites passed 74 tests; generated schema,
critical Python lint and whitespace checks passed. Logs are
`tailsitter-geometry-gate-final.log` and `tailsitter-phase0.log` beside the run.
Actual tailsitter rendering and operator pursuit acceptance are the next gate.
The [training guide](../../../../followers/05-development/ubuntu-training-platform.md#inputs-frames-and-replacement-cameras)
describes the expected sky-facing MC view, FW workflow and future multi-camera
boundary. Gimbal tracking and physical-aircraft acceptance remain later tests.
