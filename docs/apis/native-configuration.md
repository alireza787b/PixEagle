# Native configuration and OSD

Native clients use `GET /api/v1/integration/config`, authenticated with
`config:read`. The `config.operations.v1` capability advertises this resource.
The snapshot is `no-store`, version 1, with instance/runtime identity and an
opaque 64-character `config_generation`. The generation binds persisted content,
published runtime configuration, loaded definitions, and actual OSD enablement.
It is an HMAC, not a public hash oracle for sensitive configuration.

The snapshot separates saved and effective OSD state. `pending_changes` contains
at most 256 configuration paths and reload tiers, never raw values, credentials,
local model filenames or camera URLs. `apply` reports the strongest pending tier
and whether this runtime can apply it. Unknown control state is unavailable,
not proof that an aircraft is idle.

`POST /api/v1/actions/osd-set` takes `enabled: true|false` plus `instance_id`,
`runtime_id`, `config_generation`, `confirm`, and `idempotency_key`. Optional
`dry_run` validates without writing. Both `config:read` and `control:write` are
required; this preserves the existing operator OSD permission without granting
general configuration editing. Browser requests retain normal CSRF checks. It writes only
`OSD.OSD_ENABLED` through the same ConfigService persistence/audit/rollback
transaction used by dashboard settings, then updates the renderer and invalidates
its cached overlay. A failure restores saved/runtime state and renderer state.

This switch controls the **backend overlay**, not QGC's native status or target
controls. Stream/recording composition continues to use existing backend output
settings; the switch does not change those settings or promise clean recordings.
The legacy dashboard `/api/osd/toggle` retains its response shape but now delegates
to this same persistent desired-state owner. New clients must use `osd-set`;
remove the toggle alias when the dashboard migrates away from it.

`POST /api/v1/actions/config-apply` uses the same identity, generation and action
envelope with `reload_tier: immediate|tracker_restart|system_restart`. This broader
action requires `config:read` and `config:write`; an operator with only
`control:write` cannot apply other saved configuration.
Replies are normal `APIActionResponse` resources with `result.config` containing
the new snapshot. Retries with the same actor/key/request replay the action;
reusing a key for another request fails. Pending dashboard changes are observed
through the same ConfigService, not duplicated in native settings storage.

Native immediate application is limited to `OSD.OSD_ENABLED`. Other pending
immediate-tier settings are conservatively presented as system restart because
publishing Parameters alone does not prove that cached renderers or video
components reloaded. This also applies to OSD presets and style settings.

Immediate/tracker application holds the follower and tracker lifecycle barriers.
It is refused while following, Offboard, tracking, Smart mode, or camera movement
is active, and when an observed aircraft is not freshly disarmed. Tracker apply
publishes relevant saved tiers and rebuilds the configured local tracker; on
failure it restores runtime configuration and attempts to recreate the previous
tracker. Following is never resumed. Installed Smart models continue to use the
existing guarded `model-select` operation; leave Smart before broader apply.
Follower-specific changes are reported as requiring their existing lifecycle
and are not mislabeled as tracker changes.

The camera owner introduced in 4b.2 captures provider settings at startup.
The shared generated schema classifies `GimbalTracker.ENABLED`, `CONTROL_ENABLED`,
`PROVIDER`, `UDP_HOST`, `UDP_PORT`, `LISTEN_PORT`, `CONNECTION_TIMEOUT`, and
`TRACKING_STATUS_TIMEOUT` as **system restart** for both dashboard and native
clients. Adapter coordinate/estimator/recovery settings retain tracker restart.
Native clients do not duplicate the provider reload-tier mapping. A tracker
rebuild cannot claim to have reconfigured this independent camera owner.

## Shared backend restart

The maintained Linux launcher and isolated SIH launcher use the same
`src/classes/backend_supervisor.py` owner. It relaunches only its own backend
on exit code 42; camera/router/PX4 services remain running and each backend
process receives a new runtime identity and separate log. A direct Python launch
or unqualified Windows launcher reports `supervisor_not_verified` and does not
advertise `config.system_restart.v1`.

QGC presents **Restart PixEagle…** in the expanded Backend settings. It uses
`POST /api/v1/actions/system-restart` with `confirm`, `idempotency_key` and
`restart_context: {instance_id, runtime_id, config_generation}` captured from the
configuration snapshot. No frame or aircraft association is needed. The same
canonical action serves the dashboard: administrator authorization, connection
policy, durable audit, pending-change backup and lifecycle guards still apply.
Tracking, Smart detection, camera movement and following must be stopped; any
observed aircraft must be freshly disarmed. Stale confirmation is refused.

Admission and shutdown execute on the flight owner loop. Once admitted, new
camera/target operations cannot slip in during backup/audit work. Camera Stop
remains permitted. Duplicate or competing restart requests cannot clear another
request's reservation.

After an accepted request or lost acknowledgement, QGC observes the same instance
and a different ready runtime within 60 seconds without replaying the mutation.
Saved sign-in uses the system password store. Transient login transport/server
failures permit at most six attempts with a three-second backoff; credential
refusal, TLS failure and rate limiting do not automatically retry. Without saved
credentials, sign in manually. New runtime/configuration snapshots clear pending
changes authoritatively. Failure to return is reported as unconfirmed; it cannot
claim success. Tracking, movement and following never resume automatically.

Remote hardware requires `authenticated_admin_https` and a verified HTTPS
boundary; see [production reverse proxy](../setup/production-remote-reverse-proxy.md).
`local_only` remains the default; isolated SIH explicitly selects
`lab_admin_browser`. Installation geometry remains dashboard configuration,
independent of video input, tracking engine and manual camera ownership.

SIH preparation and each supervised replacement validate the complete loopback
command route: external MAVSDK at `127.0.0.1:50051`, UDP system address
`udpin://127.0.0.1:14540` and MAVLink REST at `127.0.0.1:8088`. Conflicting saved
routes refuse replacement; preserving only the UDP address is insufficient.
This is an isolated test-harness restriction, not a hardware deployment setting.

## Development demo snapshots

Prepared SIH/replay demos run copied source trees. Rebuilding QGC alone does not
update their backend route policy or config definitions. A native route returning
`route_policy_denied` with no missing scopes may indicate an old backend snapshot.
After stopping the demo backend, refresh the prepared source demo with:

```bash
python tools/refresh_native_demo_sources.py /path/to/prepared-private-demo
```

The tool backs up the prior source/definition snapshot, stages the complete new
`src` tree, updates five shared config definition files, and records source hashes
and revision in the demo manifest. It preserves the runtime `config.yaml`,
credentials, secrets, model files and media. A derived fixture with a symlinked
`src` must refresh its prepared source demo directly and separately synchronize
its definition files before restarting. Never refresh a running backend.
