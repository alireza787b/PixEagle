# Native baseline startup sequencing

The first canonical Gazebo attempt failed before arm. The observer's ten-second
discovery window began before PX4 established its DDS session; its failure
terminated the shared Agent during native time synchronization. The closed R1
result, two stopped original CIDs and disarmed ULog remain unchanged at
`reports/sitl/follower-consolidation-20261111/s7-gazebo-native-hold-cycle-r1`.

The sidecar now starts the fixed Agent in the foreground. A source-pinned,
read-only status probe in the original private primary requires exact connected,
converged and UDP loopback endpoint fields before one detached adapter launch.
The existing 45-second startup admission budget includes readiness, adapter
launch and socket arrival. Normal native discovery, parameter fixtures, full
verification, fresh pre-arm guards, 2 m gate and original-CID cleanup are intact.
No general pre-verification CLI exception or restart policy is introduced.

Synthetic regressions cover delayed and invalid readiness, process death,
private mount/workdir refusal, budget exhaustion, a lost launch reply without
retry, and failure cleanup before flight actions. The reproducible focused
command remains in `native/native-transition-baseline.md`. No Docker launch,
native build, simulation or control action was performed for this correction;
actual R2 startup remains unexecuted pending review.
