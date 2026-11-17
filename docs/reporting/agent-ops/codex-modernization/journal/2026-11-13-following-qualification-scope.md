# Following qualification scope

The operator separated native pilot/PX4 transition performance from this
following checkpoint. Retain the native-only failed captures, thresholds and
plots as airframe evidence; no new transition tuning is planned. A follower
still ends at transition entry and cannot resume without a fresh settled-phase
Start.

New evidence separates pursuit-active response and altitude from the native
maneuver after release. Altitude-disabled pursuit retains its 2 m hold gate;
normal publication retains its 100 ms gate for the entire authority-held
interval, including neutral drainage. Phase-exit fencing, obsolete commands,
late Hold, Stop and takeover remain independently checked. Relabeling an
interval or subtracting a native-only excursion cannot turn a failed ownership
test into a pass.

The next actual scenarios exercise independent moving targets, both mounts,
loss/reacquisition, retargeting, recovery and authority release. S7 remains
incomplete and live VTOL application admission remains closed. No hardware,
controller, saved setting or firmware changes are made by this documentation
update.
