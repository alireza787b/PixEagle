# Project use and release boundaries

Updated 2026-11-24.

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

## Releases and device settings

Keep shared application changes in the official repository. Merge reviewed changes
into `main`, then tag and publish the tested commit. An installation on a release
candidate can be ahead of the latest stable tag even with a clean working tree.
Record the commit as well as the version when comparing a board with GitHub.

Track factory defaults in `configs/config_default.yaml`. The installer and
Dashboard use the device’s ignored `configs/config.yaml` for saved settings.
Keep named exports, credentials, recordings and raw flight logs on the device
or in private backup storage. Use `private-profile/` for local files if they
must sit inside a checkout. Preserve that data when updating. An ordinary Git
pull fetches source and cannot upload files from the board.

Before pushing, review `git diff --cached --name-only`. Use
`git check-ignore -v -- <path>` to inspect an ignore rule and
`git ls-files -- <path>` to see whether the file is already tracked.
Previously committed files remain in Git history even after an ignore rule
is added. Review and redact evidence separately before publishing it in docs.

### Maintainer review of safety changes

Review safety fixes on the official PixEagle pull request. Verify that the
listed owner's approval is current and applies to the PR's latest commit.
After a source change, request a fresh review. SSH access, a Git author name
or a cached GitHub login cannot prove who reviewed the change. Never ask for
a private key, token or one-time code in chat.

The [code owners file](../.github/CODEOWNERS) routes changes in the listed
paths to the maintainer once it is on the PR's base branch and the PR is ready
for review. It also covers changes to the review policy. Safety changes in
other paths still require owner review under the agent guide. These rules
govern contributions to the official repository. A local clone and a live
device need their own access controls.

To enforce the review on GitHub, use a ruleset on `main` requiring a pull
request, code-owner review, and dismissal of stale approvals. Give automation
a separate, non-admin identity with no ruleset bypass. The maintainer reviews
from their own account. GitHub prevents a PR author from approving their own
PR, so agree on a separate author before activating this rule in a
single-maintainer repository. Repository approval covers the source revision
only. Device deployment is a separate authorization.
[GitHub code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)

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
