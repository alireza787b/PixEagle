# PXE-0153: Guided Update And Smart Model Recovery

Date: 2026-07-29
Status: done

Repeated guided setup now reports that an existing dashboard account and
managed-service boot policy were preserved. Fresh onboarding still asks for
credentials and optional service controls; update does not silently reset
either.

A Smart activation rejected with the typed missing-model precondition now opens
the inline model control while Classic remains the authoritative displayed
mode. The operator can add/select a model, keep Classic, or open Models. A
successful selection refreshes runtime state before one retry of the original
Smart request.

Focused installer UX passes `53`; the dashboard passes `59` suites / `402`
tests, lint, and production build. Focused docs pass `47`, Phase 0 passes `73`,
and schema remains current at `39/518`.
