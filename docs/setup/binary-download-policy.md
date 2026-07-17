# Binary Download Policy

PixEagle setup downloads two external helper binaries:

- MAVSDK Server, used by the MAVSDK Python client when an external server is
  configured.
- MAVLink2REST, used as the local telemetry HTTP bridge.

These downloads are setup dependencies only. A successful binary download does
not prove MAVSDK connectivity, MAVLink2REST telemetry, PX4/SITL behavior, HIL,
or real-world flight behavior.

## Source Of Truth

The binary source of truth is:

```text
scripts/setup/binary-manifest.env
```

The manifest pins:

- upstream repository and release URL;
- exact release tag;
- exact asset filename per supported platform;
- SHA-256 digest for every default asset PixEagle installs.

Default setup paths must not use floating `latest` release URLs or fallback tag
probing. Updating a binary means updating the manifest, docs, tests, and
checkpoint evidence in the same slice.

## Preview The Plan

Linux/macOS:

```bash
bash scripts/setup/download-binaries.sh --all --dry-run
make binary-download-plan
```

Windows:

```cmd
scripts\setup\download-binaries.bat --all --dry-run
```

Dry-run prints the resolved platform, component version, release URL, asset,
download URL, expected SHA-256, destination, and provenance-log path. It does
not download files or write `bin/`.

## Download And Verify

Linux/macOS:

```bash
bash scripts/setup/download-binaries.sh --all
```

Windows:

```cmd
scripts\setup\download-binaries.bat --all
```

The downloader writes only after the temporary file passes size/header checks
and SHA-256 verification. A requested component failure exits nonzero, including
through `make download-binaries`.

Successful verified downloads append JSON lines to:

```text
bin/binary-provenance.jsonl
```

Each entry records the component, version, platform key, asset, URL, expected
SHA-256, observed SHA-256, verification mode, destination, and timestamp. Keep
this file with SITL, HIL, field, and tester handoff evidence when those runs
depend on local MAVSDK Server or MAVLink2REST binaries.

## Overrides

Advanced operators may override pins with environment variables:

```bash
PIXEAGLE_MAVSDK_VERSION=v3.12.0 \
PIXEAGLE_MAVSDK_ASSET=mavsdk_server_musl_x86_64 \
PIXEAGLE_MAVSDK_SHA256=<sha256> \
bash scripts/setup/download-binaries.sh --mavsdk
```

Equivalent variables exist for MAVLink2REST:

```text
PIXEAGLE_MAVLINK2REST_VERSION
PIXEAGLE_MAVLINK2REST_ASSET
PIXEAGLE_MAVLINK2REST_URL
PIXEAGLE_MAVLINK2REST_BASE_URL
PIXEAGLE_MAVLINK2REST_SHA256
```

Custom URLs or assets should include a matching SHA-256. Unverified overrides
are rejected by default. Lab-only unverified acceptance requires:

```bash
PIXEAGLE_ALLOW_UNVERIFIED_BINARY=1
```

That mode records `verification_mode=unverified_override` in provenance and is
not acceptable for production, SITL success claims, HIL, field testing, or
tester handoff evidence.

## Manual Or Offline Placement

If a firewall blocks GitHub downloads, use the manifest to select the exact
asset and verify it before placing it in `bin/`.

Linux/macOS:

```bash
sha256sum <downloaded-binary>
install -m 0755 <downloaded-binary> bin/mavsdk_server_bin
install -m 0755 <downloaded-binary> bin/mavlink2rest
```

Windows:

```cmd
certutil -hashfile <downloaded-binary> SHA256
copy <downloaded-mavsdk.exe> bin\mavsdk_server_bin.exe
copy <downloaded-mavlink2rest.exe> bin\mavlink2rest.exe
```

After manual placement, rerun the downloader for the component. If the SHA-256
matches the manifest, it accepts the existing binary and appends provenance
without redownloading.
