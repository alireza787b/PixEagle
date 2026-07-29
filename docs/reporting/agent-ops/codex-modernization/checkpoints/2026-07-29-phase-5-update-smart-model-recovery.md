# Phase 5 Guided Update And Smart Model Recovery

Date: 2026-07-29
Issue: PXE-0153
Status: complete

## Scope

Close two operator-facing dead ends found during the final onboarding test:

- explain why an update does not repeat dashboard-account and service prompts;
- make a failed missing-model Smart request recoverable from the Dashboard
  without displaying a runtime mode that is not active.

## Decisions

- Fresh setup remains the only path that asks for initial browser credentials
  and optional service onboarding.
- Update preserves the existing hashed account, installed service controls,
  boot policy, and SSH-login-hint policy. It reports that preservation rather
  than resetting or re-prompting.
- The Smart/Classic toggle always reflects backend runtime state.
- Only the structured `smart_model_unavailable` precondition opens the inline
  Smart Model recovery control.
- Recovery offers a model selector, a full Models link when inventory is
  empty, and a Keep Classic cancellation action.
- After a successful selection, the dashboard refreshes authoritative mode
  state before one retry of the operator's existing Smart request. It does not
  toggle when Smart is already active or status is unknown.

## Validation

```text
tests/test_init_installer_ux.py
53 passed

dashboard/src/components/ActionButtons.test.js
dashboard/src/components/ModelQuickControl.test.js
27 passed

complete dashboard suite
59 suites / 402 tests passed

focused active documentation/setup contracts
47 passed / 166 deselected

Phase 0 API inventory and parameter reload
73 passed

schema
39 sections / 518 parameters, current
```

Dashboard ESLint and the production build pass. `bash -n install.sh`, Python
AST parsing for the touched tests, and `git diff --check` pass.

## Boundaries

- No account was rotated and no service or boot policy was changed during local
  validation.
- No model was loaded and no GPU, camera, Raspberry Pi, PX4, simulation, HIL,
  field, or aircraft behavior is claimed.
