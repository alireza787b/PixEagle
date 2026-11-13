# Sparse-axis normalization regression

S7 source review found that an absent pitch axis contributes a scale of one to
the joint roll/pitch maximum. For the native two-rotor SIH geometry this leaves
roll differential proportional to `1 / CA_ROTOR_CT`, although thrust normalizes
independently. SequentialDesaturation inherits this behavior from PseudoInverse.
The closed native-only trials still fail the unchanged 2 m altitude gate.

Patch0008 changes only absent-axis initial scales to zero and uses one when
neither roll nor pitch is active. It retains joint normalization for two active
axes and all existing yaw/thrust rules. Patch0009 and one declarative regression
record provide a dedicated functional target through the existing builder,
without a new runner or default change.

Actual R3 native execution compiled and ran all eleven cases through both real
allocator APIs and native rotor geometry. The baseline omitting only0008 had
exactly two normalization failures and nine compatibility passes; the candidate
passed eleven. Coverage includes signed sparse roll/pitch CT1/2/6.5, full-rank
quad, disabled normalization, absent axes, signed saturation/desaturation,
explicit no-renormalization, failure-flag scale freeze/recovery and analytic
metric scaling. The flag guard tests scale handling, not physical fault
detection. Actual raw exits are8/0; the outer paired builder exited0.

The two 16,436-entry source copies differ only in the production CPP. Each has
28 known generated files; source/cache integrity and identical build options
pass. Pinned astyle3.1 with actual PX4 options passes before patch freeze.
All65 focused Python tests pass with a mocked compiler; those are separate
orchestration checks. Actual evidence is
`reports/native-guidance/control-allocation-sparse-functional-20261113-r3/functional-results.json`
and the frozen closure under
`reports/sitl/follower-consolidation-20261111/software-gates-s7-sparse-allocation-normalization-proposal-r1/proposal-r3/execution-r3/`.

R1's fixture compilation failure (zero executed cases) and R2's valid seven-case
comparison remain unchanged, including their source/log/result bytes. R3 also
retains the accepted stat-only Git-index cache difference; no index/history
repair or failed-result promotion occurred.

This is software regression evidence for the unchanged production candidate,
not SIH dynamics, arbitrary failure-pattern, hardware/private-airframe or
altitude qualification. No gain, controller, plant, parameter/default, limit or
runtime authority changes are included. All previous failed aircraft verdicts
remain in force. The reviewed patch is integrated into the development series;
aircraft adoption and flight qualification remain separate gates.
