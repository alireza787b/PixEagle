# Guidance ownership after native phase exit

The user separated PX4 native pilot-maneuver qualification from following,
fallback and recovery. Existing full-window native altitude/stability failures
and raw captures remain unchanged. The focused tooling proposal reuses the
canonical Runtime preparation and vector follower, with explicit source-build
authority forwarding and truthful SIH/Gazebo provenance.

One fixed component case retains a single moving world-target clock across an
MC pursuit, native phase-exit retirement and new settled-FW Start. Pursuit
response and retained-authority/drain cadence use separate native intervals;
late writes/reactivation, uncorrelated release and unknown source attribution
are hard failures. Full native motion remains reported without peak subtraction.
Normal Stop still requires Hold; a matched native retirement does not fabricate
another Hold. Native clock epochs are distinct from status publication times.

Focused synthetic/real-tool flow regressions and a read-only replay of retained
actual ownership evidence support review. No new simulator, firmware build,
control, configuration or hardware action is performed in this slice. The exact
case, limits and reproducible preview are in `native/guidance-cycle.md`.
