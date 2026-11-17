# Pinned native resource fixtures

`airspeed-model.sdf` is the unchanged instrumentation model from
PX4/PX4-gazebo-models a15af9628536914ff7201c992fce5e3cb5d70db9,
models/airspeed/model.sdf (BSD-3-Clause upstream project).
SHA256 8e39836e6e9f749497bf2d98a0bc3f2bf583c2b0fe56078c99ea275bf8b1d7a6.
It is a test input, not a second maintained aircraft model.

`px4-ninja-jobs.mk` retains the exact Ninja-selection branch from the
PX4-Autopilot 155f415168cef08dca2f5d85d2bc258b44a589ec Makefile:85-108,
with an appended closing endif and print-only test target. It invokes no
compiler or native build. Both fixtures preserve upstream source behavior.

The corresponding upstream BSD license notices are retained alongside the fixtures.
