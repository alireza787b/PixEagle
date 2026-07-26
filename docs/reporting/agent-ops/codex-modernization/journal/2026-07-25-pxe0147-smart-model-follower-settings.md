# PXE-0147: Smart Model And Follower Settings Clarity

Smart mode previously delegated every activation failure to model construction.
When no model was available or selected, the Dashboard therefore received
generic feedback after attempting the mode transition. The saved follower
profile was also rendered as free text even though follower creation is bounded
by the canonical command catalog and factory.

The typed Smart-mode action now checks the trusted model inventory before
changing state. It distinguishes an empty inventory, an available but
unselected inventory, and a selected unsupported task. A failed preflight
returns an actionable conflict without stopping Following or toggling the
current tracker mode.

`Follower.FOLLOWER_MODE` options are now generated from
`configs/follower_commands.yaml`, matching the existing catalog-driven tracker
setting. Closed option sets remain closed in both the Settings row and detail
dialog. An extension must add a real catalog profile and factory
implementation; an old unknown value remains visible only as migration state.

Focused evidence covers `298` backend/schema/action tests, `14` Settings
frontend tests, and an up-to-date `39`-section, `518`-parameter generated
schema. The full maintained non-hardware release gates also passed. An operator
browser retest of this exact final correction and physical target evidence
remain separate next gates.
