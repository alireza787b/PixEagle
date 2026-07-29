# Phase 5 Concise Public README And Windows Quick Start

Date: 2026-07-29
Issue: PXE-0152
Status: complete

## Scope

Replace the repository front page with a concise public entry point for
beginners, engineering contributors, researchers, and potential integration
partners. Add the native Windows Core preview bootstrap without implying Linux
feature parity or flight readiness. No runtime behavior changed.

## Decisions

- Lead with one descriptive product statement, release/test/license signals,
  the current video, and direct navigation.
- Put the maintained Linux lab bootstrap and bounded Windows 11 Core preview
  before architecture or configuration material.
- State the resulting URL, first-login default, trusted-lab boundary, bundled
  video behavior, and command-publication boundary beside each quick start.
- Describe supported software surfaces without turning them into hardware,
  performance, or flight-qualification claims.
- Route installation internals, update/repair, services, networking, security,
  models, PX4, and developer procedures to their canonical documentation.
- Keep collaboration paths visible for focused contributions, research,
  commercial integration, and custom development.
- Prefer descriptive, people-first copy and image/link text over repeated search
  terms, following the official Google
  [SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
  and
  [helpful-content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content).

## Result

- README size: 336 lines / 2,378 words to 180 lines / 968 words.
- Linux quick start: mutable-main lab/development boundary, guided choices,
  authenticated result, trusted-network warning, and detailed-doc handoff.
- Windows quick start: prerequisites, PowerShell bootstrap, first login,
  `run.bat`, loopback URL, `stop.bat`, and explicit preview exclusions.
- Documentation tests now keep detailed host/source-IP, remote-media,
  setup-summary, and maintainer-walkthrough requirements in their canonical
  documents instead of forcing duplication into the README.

## Validation

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest \
  -p no:cacheprovider \
  tests/test_docs_infrastructure_consistency.py \
  tests/test_binary_download_policy.py \
  tests/test_setup_handoff_walkthrough.py \
  tests/test_setup_profiles.py \
  -k 'docs_infrastructure_consistency or binary_download_policy or setup_handoff_walkthrough or guided_install_docs or manual_setup_docs' \
  -q --strict-config

47 passed, 166 deselected
```

Independent read-only reviews found and closed the trusted-network,
ARM64-evidence, configured-video-source, and typed-command-intent wording
issues. All README local links and anchors resolve. `git diff --check` passes.

## Remaining Boundaries

- The Windows Core path remains an experimental loopback preview. A clean
  Windows 11 operator walkthrough and separate CPython 3.11 evidence remain
  under PXE-0151.
- The Linux one-line command remains a mutable-main lab/development path.
- No Raspberry Pi, Jetson, camera/gimbal, PX4, simulation, HIL, field, aircraft,
  performance, or regulatory acceptance is inferred from this documentation
  slice.
