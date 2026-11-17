# VTOL training application integration

MC Chase and Native Navigation Chase now share the native phase/session owner on
verified VTOL aircraft. Selection remains profile based; transition ends following
and requires a fresh Start. Pure-MC MAVSDK behavior is unchanged. FW Start requires
the calibrated rendered camera and retained raw source-clock attitude samples;
the latest pose is never substituted for exposure evidence.

Passive native discovery retains the original typed Start context, aircraft state
and raw attitude history on the connection. Older replies cannot clear a newer
context. Repeated reads retain original measurement age. A rejected full native
observation cannot authorize publication by comparing equal cached pose alone.
The bounded first-pair wait cannot extend the original request deadline.

Software checks and source/runtime manifests are retained under
`reports/sitl/follower-consolidation-20261111/software-gates-training-native-observation-r1/`.
The initial focused set passed 177 tests, and API/schema/alignment/binding checks
passed 206. The combined rendered-camera/native-control flight checkpoint remains
pending; component camera and adapter results are not full-application evidence.
Public defaults, physical profiles and aircraft firmware installation are unchanged.

The new MC camera-board v2 descriptor uses the current pinned stock build without
changing any MC aircraft/world/camera geometry. The standard VTOL courtyard v3
includes the independently verified camera source and encoder-free overlay. Both
use the same token-owned launcher and preserve historical failed runs and logs.
