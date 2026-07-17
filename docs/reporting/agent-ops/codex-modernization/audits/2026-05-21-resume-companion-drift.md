# Resume Companion Drift Audit

Date: 2026-05-21  
Scope: resume after pause; companion tool drift check before continuing PXE-0016.

## Resume Position

The current PixEagle worktree is intentionally dirty from Phase 0 modernization
slices. The interrupted PXE-0016 gimbal provider patch did not leave a partial
`src/classes/gimbal_provider.py` file. The active next slice remains Phase 1
PXE-0016 unless the maintainer intentionally prioritizes Offboard safety first.

## Companion Repositories Checked

### MavlinkAnywhere

- Local path: `/home/alireza/mavlink-anywhere`
- Local branch state after fetch: `main...origin/main [behind 4]`
- Latest remote tag checked: `v3.0.10`
- New remote commits since local checkout:
  - `95d96ed feat: add fleet mavlink profile control`
  - `35f74ba chore: release mavlink anywhere v3.0.9`
  - `1027be4 docs: polish public branding and security posture`
  - `1f7c766 chore: release 3.0.10 branding refresh`

Relevant impact:

- Fleet profile APIs are now a first-class MDS automation surface:
  `/api/v1/profiles/summary`, `validate`, `diff`, `import`, `apply`, and
  reference-draft promotion.
- Remote mutating dashboard/API requests require `MAVLINK_ANYWHERE_API_TOKEN`;
  loopback remains usable for local maintenance.
- `fleet-merge` preserves hardware input and local endpoints; `fleet-strict`
  can prune local outputs only after advanced confirmation.
- PixEagle docs should keep default ports already adopted earlier:
  MAVSDK `127.0.0.1:14540`, MAVLink2REST router output `127.0.0.1:14569`,
  local endpoint `127.0.0.1:12550`, GCS listen `0.0.0.0:14550`, TCP `5760`,
  dashboard `127.0.0.1:9070`.

### MAVSDK Drone Show

- Local path: `/home/alireza/mavsdk_drone_show`
- Local branch state after fetch: `main...origin/main [behind 74]`
- Latest remote tag checked: `v5.5.6-sitl-image-refresh`
- Current `deployment/defaults.env` pins:
  - `MDS_DEFAULT_MAVLINK_ANYWHERE_REF=v3.0.10`
  - `MDS_DEFAULT_SMART_WIFI_MANAGER_REF=v2.1.11`
  - `MDS_DEFAULT_SMART_WIFI_MANAGER_MODE=fleet-merge`
  - `MDS_DEFAULT_SMART_WIFI_MANAGER_IMPORT_MODE=merge`

Relevant impact:

- Fleet Ops sidecar controls and profile reconciliation have advanced
  significantly since the May 7 checkpoint.
- Connectivity management treats Smart Wi-Fi Manager as an optional node-local
  sidecar; OS-managed Ethernet/cellular/VPN links should use backend `none`.
- Smart Wi-Fi profile rollout now prefers `fleet-merge` so emergency/local
  field profiles are preserved unless an operator deliberately chooses stricter
  policy.
- SITL image guidance changed again in `v5.5.6`; PixEagle's later PX4/SITL
  harness must re-check the current MDS docs before implementation.

### Smart Wi-Fi Manager

- Local path created for review: `/home/alireza/smart-wifi-manager`
- Local branch state after clone: `main...origin/main`
- Latest remote tag checked: `v2.1.11`
- Recent relevant changes:
  - fleet Wi-Fi profile control
  - secured NetworkManager profile repair
  - release hardening for fleet Wi-Fi profiles
  - public branding/security posture docs

Relevant impact:

- The tool is local-first and not MDS-specific.
- Runtime files are canonical:
  - config: `/etc/smart-wifi-manager/config.json`
  - status: `/run/smart-wifi-manager/status.json`
  - state/control: `/var/lib/smart-wifi-manager`
  - logs: `/var/log/smart-wifi-manager/smart-wifi-manager.log`
- Dashboard/API default is `127.0.0.1:9080`.
- Remote mutating fleet profile requests require
  `SMART_WIFI_MANAGER_API_TOKEN`.
- Profile policy modes are `observe`, `local`, `fleet-merge`, and
  `fleet-strict`; dry-run before apply is the safe fleet workflow.
- Public repositories must not store real Wi-Fi passwords. Prefer
  `password_file` paths for durable fleet policy.

## PixEagle Plan Impact

- PXE-0022 remains open and now explicitly tracks the latest companion pins and
  token-gated sidecar mutation behavior.
- No PixEagle runtime code should depend on stale MDS `v5.3.x`,
  MavlinkAnywhere `v3.0.8`, or Smart Wi-Fi Manager `v2.1.8` assumptions.
- The current active implementation slice, PXE-0016 gimbal provider
  abstraction, is not blocked by this companion drift.
- Before API/MCP/devops slices, re-review MDS `origin/main` again and align
  PixEagle with the current sidecar profile, auth, dry-run/apply, and evidence
  patterns.
