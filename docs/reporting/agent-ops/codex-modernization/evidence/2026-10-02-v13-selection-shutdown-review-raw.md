# V13 selection and shutdown AI review observations

Reviewer: `/root/v13_selection_shutdown` (AI implementation/review agent).
Date: 2026-10-02. These are software review observations, not physical operator
acceptance or camera/aircraft qualification.

## Review notes retained during implementation

- Selection validation must precede native
  `lifecycle_reservation(cancel_manual=True)`. Validation inside the camera
  executor alone is too late to preserve manual ownership on an invalid tap.
- The Dashboard facade also rejected camera selection during following and
  skipped adapter geometry validation in dry-run. Both callers need the same
  provider preparation/dispatch contract.
- A fresh video-processing timestamp cannot establish a fresh camera-angle
  sample. Actual angle receipt, sequence, provider identity and post-LOC
  observation are required; firmware without request IDs cannot prove target
  identity from timestamp ordering alone.
- Hard geometry and safety refusals must not become ordinary bounded target
  loss. Otherwise continuity could retain horizontal pursuit after the
  follower itself rejected its operating geometry or altitude envelope.
- Ordinary-loss commands need safety validation without slew. Loss retains
  immediate zero yaw/vertical behavior and records the actually submitted
  horizontal intent as the next shaping/recovery baseline.
- A shared Future fulfilled by the original Stop caller is insufficient:
  `_run_on_flight_event_loop` propagates caller cancellation to the owner
  coroutine. Teardown needs its own shielded task and retained outcome.
- Moving teardown into a task changes watchdog cancellation identity. A
  watchdog that initiated Stop must be allowed to finish its awaited handoff,
  rather than being cancelled by its own cleanup.
- Native handoff history needs captured session/aircraft identities.
  `stopped` must remain distinct from `confirmed_hold`, particularly for local
  preview and inhibited aircraft actions.
- Final native selection admission must recheck application shutdown. The
  initial check is insufficient when shutdown begins during the asynchronous
  camera handshake while waiting for the follower barrier. Final commit now
  refuses LOC dispatch in that case.

## Regression evidence

Focused command:

```bash
PYTHONPATH=src .venv/bin/pytest \
  tests/unit/trackers/test_gimbal_control.py \
  tests/unit/core_app/test_native_target_operations.py \
  tests/unit/core_app/test_app_controller_offboard_safety.py \
  tests/unit/core_app/test_api_v1_gimbal_control.py \
  tests/unit/core_app/test_target_continuity.py \
  tests/unit/core_app/test_native_following.py -q --tb=short
```

Result: **448 passed**, two existing dependency deprecation warnings, 14.50 s.
The regressions include Classic/Smart edge refusals in both entry paths,
native validation before ownership cancellation, post-selection sample age and
provider rejection, both gimbal followers' submitted-command boundary,
hard geometry/safety handoff, retained native history, concurrent Stop,
original-caller cancellation and watchdog waiter completion.

No camera packets, physical motor motion or aircraft commands were sent by
these mocked tests. Full backend/dashboard/QGC gates and isolated SIH evidence
are separate checkpoint evidence.

Follow-up after the final shutdown-commit guard: **133 camera/native target
tests passed** (11.45 s), including admission before shutdown and rejection at
commit. The route inventory/test-hygiene gate passed **51 tests** (2.36 s).
Three pre-existing test send stubs were rewritten as named callbacks to pass
the enforced test-hygiene gate without changing their behavior.
