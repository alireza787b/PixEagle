# Packaged Gazebo sensor variant — 2026-11-13

The existing strict simulator builder can select one versioned packaged
`quadtailsitter-no-pitot-v1` derivative. It removes only the pinned airspeed
sensor block after verifying the stock source/package, preserving the passive
housing and plant. The recipe and image bind descriptor/source/output hashes;
all other resource differences remain errors. Stock remains the default.

The shared compiler command now forwards `j=2`, which PX4's pinned Makefile
requires to bound Ninja jobs. Validation uses the explicitly selected authority's
builder bytes; actual builds refuse mixed executing/authority builder versions.
Historical 0001–0007 evidence remains separate from current 0001–0009 inputs.

Portable source fixtures exercise sensor-only deletion, immutable package
binding, unknown/extra-difference rejection and actual Make job forwarding
without invoking a compiler or Docker. The old manifest receives a separate
read-only replay against its retained labels. No real preparation, build,
simulation or hardware action occurred. Startup sensor policy, native
readiness wiring and flight qualification remain a later reviewed slice.

Root renews 684 combined builder, verifier, native-runner, functional-orchestration
and documentation checks. Malformed manifest/build objects retain typed refusal
before external calls. Derived negative-control authorities now preserve the
selected repository's exact regular builder bytes; the shared helper supplies
this once, without per-report copying or an executing-builder fallback. The
initial combined failure and both reviewed proposal packets remain retained.
