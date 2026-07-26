# Phase 5 Checkpoint: Smart Model And Follower Settings Clarity

Date: 2026-07-25
Issue: PXE-0147
Status: implementation and local release validation complete

## Problem

The Smart toggle did not explain whether the operator needed to upload a model,
select an existing model, or replace an unsupported task. The saved follower
profile was a free-text Settings value despite the runtime's closed follower
catalog, and the parameter detail dialog could bypass a closed enum schema.

## Changes

- Added a non-mutating Smart model preflight in the existing model API/service
  boundary.
- Return typed `409 smart_model_unavailable` action failures for empty,
  unselected, unreadable, or unsupported model states.
- Keep Following and the current tracker mode unchanged when preflight fails.
- Generate follower labels, values, and descriptions from
  `configs/follower_commands.yaml`.
- Keep unknown historical values visible as migration state while refusing new
  arbitrary values unless `allow_custom_values` is explicitly enabled.
- Aligned model setup and follower extension documentation with those
  contracts.

## Validation

- Backend action, generated-schema, route-inventory, and reload suite:
  `298 passed`.
- Dashboard Settings focused suite: `2 suites`, `14 tests passed`.
- Schema check: `39` sections, `518` parameters, up to date.
- Maintained non-hardware backend suite: `3,611 passed`, `47` expected
  platform/dlib skips, `1` deselected external marker.
- Phase 0: `492 passed`.
- Dashboard: `57` suites, `379` tests passed; production build passed.
- Python compile, generated API provenance, Markdown links, shell syntax, and
  `git diff --check`: passed through the maintained gates.

## Evidence Boundary

These checks prove API error classification, no-state-change ordering, schema
generation, and Settings enum behavior. They do not execute an uploaded model,
prove inference quality, or validate a follower, PX4, Raspberry Pi, field, or
aircraft response.

## Next Gate

Verify in a browser that an empty Smart inventory gives upload guidance, an
existing unselected model gives selection guidance, and the Follower setting
presents only catalog profiles. Physical follower, PX4, Raspberry Pi, and
aircraft acceptance remain separate.
