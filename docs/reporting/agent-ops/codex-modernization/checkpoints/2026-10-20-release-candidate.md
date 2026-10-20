# PixEagle 7.5.0-rc.1 source publication

This candidate includes the changes through `ab7f35f`, refreshed generated API
inventory hashes and aligned backend/Dashboard/setup version metadata. It is a
prerelease, not stable native-WebRTC or flight qualification. Normal backend
advertisement of native QGC WebRTC remains disabled.

## Renewed software evidence

| Gate | Result |
| --- | --- |
| Backend unit suite, CI exclusions | 3,799 passed; 11 optional GStreamer tests skipped; 14 subtests passed |
| Backend integration suite, CI exclusions | 196 passed |
| Phase 0 guardrails, first run | 154 passed; stale generated API hashes detected |
| Generated inventory repair | Regenerated through the existing tool; all 13 inventory tests passed |
| Complete Phase 0 guardrail rerun | 155 passed after the generated inventory repair |
| Version/about consistency | 6 passed after metadata alignment |
| Dashboard tests | 64 suites / 493 tests passed |
| Dashboard production build | Passed again with release-candidate metadata |
| Configuration schema | Current, 606 parameters |
| Fatal-error Python lint / shell syntax | All `src`, `tests`, `scripts` passed the fatal-error lint selector; all setup shell scripts parsed |

Optional native runtime tests need their configured GI/GStreamer interpreter;
the ordinary Core test environment skips them. Previously recorded encrypted
native tests and Pi comparisons remain separate evidence in the native video
qualification report. Warnings include existing Starlette deprecations. The
first guardrail failure was generated provenance drift, not a new route or a
reason to weaken the generator check.

## Configuration and deployment

Factory remains video-file/OpenCV, PixEagle CSRT, constant-position following,
no gimbal, altitude safeguards and circuit breaker enabled. Video defaults are
Automatic 720p/20 FPS, 12 FPS/75% startup, JPEG 70–85 and 8,000 kbps configured
payload allocation. Saved installations adopt changes through Config Sync.

The private Pi was last updated to `ab7f35f` through the normal stopped-runtime
updater and verified on both LAN and Wi-Fi. Its source-built OpenCV/GStreamer,
camera engine, vertical geometry, follower gains and saved 720p/15 FPS profile
were preserved. Circuit breaker was explicitly enabled for the bench and backed
up. The normal service was active/enabled at that verification. The board was
unreachable when packaging resumed, so this candidate is not claimed as deployed
to it. Reconnect, run the normal updater against `release/7.5.0-rc.1`, verify the
exact revision/configuration and only then shut down for the private SD image.

Private configuration/rollback copies and SD tools are staged in Desktop
`PixEagle-QGC-final-2026-10-20-rc1/`. They are not public release assets. An image
contains credentials and machine identity; do not publish it or boot clones with
duplicate fixed addresses/SSH identity. No new card image was made in this slice.

## Publication boundaries and next gates

Publish the source branch and annotated `v7.5.0-rc.1` tag as a GitHub prerelease;
open a draft PixEagle PR for CI/review. Do not merge/promote it to stable while
the following gates remain unresolved: independent weak-link pixel integrity,
browser/native policy parity, simultaneous-client capacity allocation, startup
recovery, sustained power/cooling and native Windows/Android qualification.

QGC separately merges official master through `6133ce6d2` and builds matching
Windows/Linux/Android candidates. Its custom application gets no public PR or
public GitHub release. Android currently uses a temporary CI signing identity,
not a persistent production signing key. Artifact creation does not establish
physical tablet acceptance. Retain exact source revisions, checksums, CI links
and these limitations with the downloaded package set.
