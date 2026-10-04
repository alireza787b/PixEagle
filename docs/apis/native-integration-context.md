# Native client connection and aircraft association

Slice 1 adds an authenticated observation contract for the PixEagle QGC custom
build. It does not grant or enable tracking, following, arming, Offboard,
mission, gimbal, or flight control. Both routes remain blocked, non-callable
MCP candidates.

## Routes and authentication

| Method/path | Operation ID | Behavior |
| --- | --- | --- |
| `GET /api/v1/integration/context` | `get_integration_context` | Snapshot only; never opens a MAVSDK connection. |
| `POST /api/v1/integration/connection` | `observe_integration_connection` | Explicit observational discovery; body must be `{}`. Returns the same context. |

Both require a real browser session or bearer credential with **both**
`status:read` and `telemetry:read`. Same-host `local_compat` access is deliberately
insufficient and returns `401 native_credentials_required`. Existing Host,
Origin, exposure, token expiry/revocation, and scope checks still apply. There
is no query-string token transport. Successful responses use `Cache-Control:
no-store`; credentials and session IDs are absent from the context.

Native clients may use the existing `/api/v1/auth/session`,
`/api/v1/auth/login`, and `/api/v1/auth/logout` workflow. Login accepts
`{"username":"...","password":"..."}` and sets the HttpOnly cookie (default
name `pixeagle_session`). Its response includes `csrf_header_name`,
`csrf_token`, and `expires_at`; use the returned header name (default
`X-PixEagle-CSRF`) for POST discovery and logout. Bearer clients attach an
Authorization header. Credentials stay scoped to the configured backend
origin and must not be copied to redirects or media endpoints automatically.

The POST also requires durable mutation audit and session-bound CSRF. It is
idempotent observation: existing connected MAVSDK ownership is reused,
concurrent requests serialize through the existing flight-loop lifecycle
barrier, and no follower is constructed. It calls
`PX4InterfaceManager.connect()` and reads `info.get_identification()`, never
`AppController.connect_px4()` (which starts following). Discovery does not
require lifting the command circuit breaker. Total request execution is
bounded to 17 seconds, including the lifecycle-barrier wait. A timeout returns
typed `504 native_discovery_timeout`; unavailable observation returns typed
`503 native_context_unavailable`. Cancellation is forwarded to the existing
owner loop and identity completions from a superseded connection are ignored.
If that owner loop has not started, discovery fails without binding the API
loop as a replacement owner. During an existing follow session, verification
only reads the already-connected identity; it cannot restart/reconfigure that
session's telemetry or reconnect its lost command link.

## Context version 1

| Field | Meaning |
| --- | --- |
| `contract_version` | String `"1"`; reject incompatible versions. |
| `backend_version` | PixEagle application version. |
| `instance_id`, `instance_id_source` | Configured `PIXEAGLE_INSTANCE_ID`, or a SHA-256 identifier of the resolved installation path with source `local_path`. |
| `runtime_id` | Opaque process-lifetime UUID; changes on backend restart. |
| `capabilities` | Includes `integration.context.v1`. |
| `command` | Observed MAVSDK identity, connected state, opaque string connection generation. |
| `telemetry` | Observed telemetry identity, connected state, measured freshness, opaque string connection generation. |
| `association` | `verified` and machine-readable `reason_codes`. |
| `video` | Additive slice-2 stream/source epochs, protocol path, and exact encoded dimensions when available; capture freshness comes from each JPEG, and `geometry_verified` remains false. See [frame provenance](native-frame-provenance.md). |
| `permissions` | Current principal kind and exact granted scope names. |
| `readiness` | Connection readiness and a conservative `following_allowed:false` summary. Slice 4a clients read the separate [native following resource](native-following-operations.md) for current profile, target and Offboard readiness; the context read does not wait for model or target operations. |

Set a unique stable `PIXEAGLE_INSTANCE_ID` for each deployment. The local-path
fallback identifies a local installation only; it is **not globally unique**,
does not authenticate a remote host, and may collide across machines using the
same path. Duplicates must block association until explicitly configured.
TLS validation and the existing authentication boundary remain responsible
for the remote endpoint's trust.

Aircraft identity objects include `source`, `connected`, `fresh`,
`connection_generation`, nullable integer `system_id`/`component_id`, nullable
decimal-string `autopilot_uid`, and nullable string `hardware_uid`. Command
`fresh` is false/unused; measured freshness is a telemetry requirement.
Clients compare generation strings for equality; they must not parse them as
numbers. Every UID is a lossless unsigned 64-bit decimal string; zero,
floating-point values, booleans, and out-of-range values are unknown.

MAVSDK `info.get_identification().legacy_uid` is the observed command UID and
corresponds to QGC's `AUTOPILOT_VERSION.uid`. `hardware_uid` represents UID2
and is not interchangeable with it. Command system/component IDs remain null
because this MAVSDK information interface does not expose the target IDs;
MAVSDK's own server IDs and configured link addresses are never used as proof.

## Explicit telemetry routing and freshness

`MAVLink.MAVLINK_SYSTEM_ID` and `MAVLink.MAVLINK_COMPONENT_ID` select the
autopilot telemetry route; both default to 1 and accept integers 1–255. They
apply on process restart to the aggregate data paths and all four follower
message reads (attitude, altitude, local velocity, and VFR HUD throttle). These
settings replace the embedded vehicle-1 assumption. Existing
`MAVLINK_DATA_POINTS` paths are rebased to this selected vehicle/component;
deployments that previously customized those path prefixes must set the two
explicit IDs when migrating. The selected heartbeat also supplies arm status;
component 191 is no longer implicitly preferred.

Configured IDs do not establish association. The selected component must
actually contain an observed PX4/ArduPilot heartbeat and a nonzero
`AUTOPILOT_VERSION.uid`. Its heartbeat `status.time.counter` must advance
between local observations before `telemetry.fresh` becomes true. Freshness
expires after `MAVLINK_STALE_TIMEOUT_S` measured with the monotonic clock;
successful HTTP reads of an unchanged cached payload do not extend it.
Heartbeat counter reset, observed boot-time rollback, UID replacement, loss,
and stale recovery invalidate the telemetry generation. A duplicate observed
UID under another vehicle/component is ambiguous and fails closed.

Association additionally requires the command link to be connected and its
nonzero observed UID to equal telemetry's UID. The native client must then
match that UID and telemetry system ID to its currently selected QGC vehicle
and reject duplicate IDs, stale responses, and endpoint/profile changes.
Generation/runtime changes invalidate a previous binding. Examples of blocking
reasons are `command_identity_unknown`, `telemetry_heartbeat_unconfirmed`,
`telemetry_stale`, `telemetry_identity_ambiguous`,
`telemetry_route_unobserved`, and `aircraft_identity_mismatch`.

MAVSDK-only telemetry currently has no independently observed system ID in
this contract, so it reports `telemetry_route_unobserved` and cannot bind to
QGC. Missing AUTOPILOT_VERSION or heartbeat-counter metadata also remains
unverified. Slice 1 does not silently fall back to a configured sysid or a
user-supplied claim. Slice 2 adds [video frame provenance](native-frame-provenance.md);
image-to-aircraft geometry remains unverified. This endpoint cannot authorize
target selection.

## Verification boundary

Mock tests cover auth/CSRF/revocation, audit denial, explicit discovery,
lossless UID parsing, mismatches and duplicates, stale cached telemetry,
identity/generation changes, reboot evidence, explicit routing, cancellation,
and lifecycle serialization. No actual MAVSDK server, aircraft, camera,
SITL/HIL, or deployment is needed or claimed.

The MAVLink2REST heartbeat counter shape follows its
[upstream API documentation](https://github.com/mavlink/mavlink2rest#api).

For isolated QGC UI checks, `tools/native_integration_fixture.py` launches only
the real FastAPI authentication/integration/status and JPEG routes around mocked
aircraft observations and numbered synthetic pixels. It binds loopback, writes
security audit into a temporary directory, and creates no deployed users,
services, MAVSDK connections, camera, or flight runtime:

```bash
.venv/bin/python tools/native_integration_fixture.py \
  --port 8091 --system-id 1 --uid 18446744073709551001 \
  --instance-id fixture-one
# In a second terminal/process:
.venv/bin/python tools/native_integration_fixture.py \
  --port 8092 --system-id 2 --uid 18446744073709551002 \
  --instance-id fixture-two
```

The ephemeral test-only login is `operator` / `fixture-only`. `--stale` or
`--telemetry-uid 22` simulate blocking states. Keep each endpoint's cookie jar
separate; cookie domains do not isolate ports. Stop these fixture processes
after validation. Their identities and freshness are synthetic, not aircraft
or actual runtime evidence.

For video/status without synthetic aircraft observations, use `--no-aircraft`
instead of `--system-id` and `--uid`. Authenticated media and status remain
available, while command/telemetry identities remain unknown and disconnected
even after discovery. This supports a clearly labelled companion preview;
aircraft association and following stay unavailable. See the
[camera-free fixture commands](native-frame-provenance.md#camera-free-validation-fixture).
