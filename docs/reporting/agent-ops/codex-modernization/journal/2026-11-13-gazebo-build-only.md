# Gazebo build-only preparation

Date: 2026-11-13. Base: PixEagle `f73bb25c2`. Work isolated from the active PX4
allocator regression and root worktree. No native patches or firmware authority
were adopted by this slice.

The existing simulator builder now has an explicit Gazebo recipe and CLI target.
Source/extension verification, offline compilation, artifact extraction from a
stopped container, hashes and image labels remain shared. SIH defaults/manifest
shape remain unchanged; the strict builder-source fingerprint still changes
when its implementation changes. Gazebo manifests are distinct and cannot be
passed to an unchanged SIH validator/runner.

The recipe pins the stock quad tailsitter/model submodule and plugin dependency.
Packaged model/world/server hashes are checked against source provenance.
An official PX4 Harmonic amd64 development image was identified through registry
manifest/config/SPDX reads and pinned for both compiler and initial runtime;
no custom Apt image or layer pull was performed. The dependency-image revision
is recorded separately from the firmware revision. Details and reproduction
commands are in [native build notes](../../../../../native/gazebo-build.md).

Validation: 88 shared SIH/native/functional build and Gazebo target/resource/
manifest/no-launch tests pass with mocked compiler/image outputs. The minimum
API route/config reload gate passes 74 tests (one existing Starlette deprecation
warning). Schema check, touched Python syntax, CI-selected flake8 checks and
`git diff --check` pass. The first schema invocation selected system Python
without ruamel; rerunning with the existing project venv passes.

Not run: image pull/install, submodule fetch, real build, PX4/Gazebo execution,
flight, service/hardware access. Next gates are real dependency/build validation,
isolated Gazebo runtime verification, native stable flight/both transitions,
explicit no-pitot test predicate, then authority handoff and follower scenarios.
Existing Duo failures, S7 closure and S8 unavailability remain unchanged.
