# Project use and release boundaries

Updated 2026-10-04.

## PixEagle public project

The PixEagle source repository and its authored documentation are released
under the [Apache License 2.0](../LICENSE). The license, copyright notices,
third-party notices, model cards, and artifact-specific terms travel with the
corresponding source or release. Models, datasets, downloaded binaries,
camera firmware, PX4, QGroundControl, and other dependencies may have separate
terms.

PixEagle is provided **AS IS**. It is not certified avionics and does not make
claims about tracker accuracy, aircraft control, field safety, regulatory
compliance, or suitability for a particular vehicle or mission. Operators and
integrators are responsible for independent review, local law, failsafes,
abort paths, controlled testing, and any deployment decision. The Apache
License contains the applicable warranty disclaimer and limitation of
liability.

The project does not endorse, authorize, certify, or support military or other
operational use through a README, demo, test profile, or integration example.
Educational, research, and controlled development examples are not flight or
mission authorization. Contact the maintainer before relying on a custom
deployment or requesting project-specific integration information:
[p30planets@gmail.com](mailto:p30planets@gmail.com).

### Apache 2.0 licensing note

Apache 2.0 grants broad rights to use, reproduce, modify, and distribute the
licensed work, subject to its stated conditions. It does not contain a
military-use or non-educational-use field-of-use restriction. Therefore this
project cannot truthfully add such a restriction while continuing to describe
the same source as Apache-2.0 licensed. The non-endorsement and no-support
statement above records project policy; it is not an additional condition of
the Apache license. If the copyright holders require a legally binding
field-of-use restriction, they must adopt a separately reviewed licensing
model before changing the public license or publishing a restricted edition.

## Customized QGroundControl integration

The PixEagle-native QGroundControl work is a private/custom integration branch
and test bed. It is **not currently a public QGroundControl release**, and no
custom installer, Windows package, Android package, or public QGC PR should be
treated as released from this worktree. The documentation records architecture,
configuration, validation evidence, and remaining gates so a future release
can be reviewed rather than inferred from a local build.

Until a future release decision is made, requests for this customized QGC
integration should be directed to the maintainer. The public PixEagle project
and its normal Dashboard remain separate from this unreleased native-QGC work.

Do not publish credentials, private camera addresses, local logs, generated
handoff files, or test artifacts that contain secrets. Release candidates must
complete the documented platform, hardware, compatibility, licensing, and
review gates and must preserve QGroundControl and third-party notices.
