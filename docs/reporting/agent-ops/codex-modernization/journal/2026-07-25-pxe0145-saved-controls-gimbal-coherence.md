# PXE-0145: Saved Tracker Controls And Gimbal Coherence

The dashboard previously treated tracker and follower selections as temporary
runtime choices, while the Smart model control was visible in a general
diagnostics area. Operators could not tell which choice would survive a
restart, and the tracker handoff was described with restart/error language
although the process itself did not need to reboot.

The dashboard now presents contextual controls: Classic mode exposes the
schema-driven tracker selector, Smart mode exposes installed detection models,
and Tracker/Follower changes use explicit save actions. Tracker persistence
uses the same validated configuration transaction as other settings. A live
tracker replacement requires a new target session, not a process restart.

External gimbal providers can deliver angle and target-lock data in separate
packets. The provider now retains each component with its own timestamp and
composes a coherent snapshot only from independently fresh components.
`GimbalTracker.get_output()` reads the published sample without invoking another
update or mutating counters. Angles remain visible for diagnosis when the lock
status is stale, but the canonical follower-readiness contract remains
fail-closed.

Local evidence covers the backend/API/config contracts, gimbal packet
coherence, the full dashboard suite (`56` suites, `375` tests), the production
build, schema validation (`39` sections, `518` parameters), Python checks, and
diff validation. The remaining acceptance boundary is real camera/gimbal
packet evidence and an operator retest; no PX4, Raspberry Pi, field, or
aircraft behavior is claimed.

The first beta.30 push exposed a missing regenerated API tool-candidate
provenance artifact in the repository Phase 0 guardrail. The exact guardrail
suite passed after regeneration; beta.31 carries that generated artifact and
does not change runtime behavior.
