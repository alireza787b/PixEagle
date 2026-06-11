# MavlinkAnywhere Integration

MavlinkAnywhere is the recommended way to install and manage `mavlink-router`
for PixEagle. It is not MAVLink2REST. MavlinkAnywhere owns MAVLink routing,
local service endpoints, the optional routing dashboard, and the
`mavlink-router.service` systemd unit. MAVLink2REST remains a separate telemetry
HTTP bridge that consumes one of those routed MAVLink endpoints.

## Current Default Topology

| Consumer | Endpoint | Mode | Purpose |
|----------|----------|------|---------|
| PixEagle MAVSDK | `127.0.0.1:14540/udp` | explicit local output | Offboard commands and optional MAVSDK telemetry |
| MAVLink2REST | `127.0.0.1:14569/udp` | explicit local output | HTTP telemetry bridge input |
| Local tools | `127.0.0.1:12550/udp` | explicit local output | Debugging and local monitoring |
| QGroundControl | `0.0.0.0:14550/udp` | server-mode listener | Ad-hoc field GCS access |
| TCP clients | `0.0.0.0:5760/tcp` | TCP server | Dynamic or multi-client MAVLink access |
| MavlinkAnywhere dashboard | `127.0.0.1:9070/tcp` | local-only HTTP | Router management UI |

`gcs_listen` on `14550/udp` is convenient for field access, but it is server
mode and tracks the last sender. Do not treat it as deterministic multi-client
fanout. For deterministic remote access, add explicit normal-mode endpoints or
use the TCP server on `5760/tcp`.

## Install And Configure

```bash
git clone https://github.com/alireza787b/mavlink-anywhere.git
cd mavlink-anywhere
git fetch --tags origin
git checkout <validated-tag-or-commit>

sudo ./install_mavlink_router.sh
sudo ./configure_mavlink_router.sh
```

The configure step detects the host platform, checks serial prerequisites,
writes `/etc/mavlink-router/main.conf`, manages
`/etc/default/mavlink-router`, installs or refreshes
`mavlink-router.service`, and installs the optional
`mavlink-anywhere-dashboard.service`.

On Raspberry Pi, serial-port fixes can require a reboot. Re-run the configure
step after the reboot.

## Headless PixEagle Profile

For a companion computer with a PX4 UART input and the current PixEagle local
service endpoints:

```bash
sudo ./configure_mavlink_router.sh --headless \
  --uart /dev/ttyS0 \
  --baud 57600 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550"
```

For SITL or another UDP MAVLink source:

```bash
sudo ./configure_mavlink_router.sh --headless \
  --input-type udp \
  --input-address 0.0.0.0 \
  --input-port 14550 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550"
```

PixEagle then uses:

```yaml
PX4:
  SYSTEM_ADDRESS: udp://127.0.0.1:14540

MAVLink:
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088
```

The PixEagle `scripts/components/mavlink2rest.sh` launcher consumes
`udpin:127.0.0.1:14569` by default and binds the MAVLink2REST HTTP API to
`127.0.0.1:8088` by default.

## Dashboard

MavlinkAnywhere installs the dashboard bound to localhost:

```text
http://127.0.0.1:9070
```

Loopback access is the default and preferred operation mode. Expose the
dashboard only on a trusted admin network or VPN, or use an SSH tunnel.
Non-loopback exposure must also configure browser authentication and a machine
API token:

```bash
sudo ./configure_mavlink_router.sh --install-dashboard \
  --dashboard-listen 0.0.0.0:9070 \
  --dashboard-auth-user operator \
  --dashboard-auth-password-file /root/mavlink-dashboard-password \
  --dashboard-api-token-file /root/mavlink-api-token
```

The dashboard can inspect router status, manage endpoints, preview and apply
routing profiles, restore the last good dashboard-managed backup, stream logs,
and control `mavlink-router.service`.

Remote browser mutations use Basic Auth plus `X-Sidecar-CSRF`, which the
bundled dashboard adds. Remote machine mutations use
`MAVLINK_ANYWHERE_API_TOKEN` as a bearer token. Do not place credentials in
PixEagle config, source control, docs, reports, MCP client files, shell history,
or command-line arguments. Open-lab mode is an isolated disposable-lab
exception, not an accepted field or shared-host configuration.

## Profile Reconciliation

MavlinkAnywhere profile automation is external to PixEagle. Use redacted
summary/validation reads first, import only with `dry_run=true`, review the
stored plan and warnings, then apply on the same running dashboard instance
with its confirmation token and required risk acknowledgements. Dry-run plans
are process-local and are lost when the dashboard restarts.

Policy modes:

| Mode | Behavior |
| --- | --- |
| `observe` | validate/report only; apply is rejected |
| `local` | node-local policy remains authoritative; fleet apply is rejected |
| `fleet-merge` | apply baseline endpoints while preserving local extras and hardware input |
| `fleet-strict` | prune non-baseline outputs only after advanced confirmation; preserve hardware input |

`fleet-merge` is the preferred rollout mode. PixEagle must not proxy these
mutation APIs into a broad API or MCP tool. See the
[Companion Runtime Contract](../../architecture/companion-runtime-contract.md)
for auth, version, evidence, and ownership rules.

## QGroundControl

With the default `gcs_listen` endpoint, configure QGroundControl as:

```text
Comm Links -> Add -> UDP
Server: <device-ip>
Port: 14550
```

Use this for ad-hoc field access. For multiple simultaneous remote consumers,
prefer explicit endpoints or TCP `5760`.

## Update Procedure

```bash
cd ~/mavlink-anywhere
git fetch --tags origin
git checkout <validated-tag-or-commit>

sudo ./configure_mavlink_router.sh --install-dashboard
```

Run `sudo ./install_mavlink_router.sh` during an update only when the
`mavlink-routerd` binary itself must be rebuilt or reinstalled.

If the dashboard is intentionally exposed, preserve the explicit bind:

```bash
sudo ./configure_mavlink_router.sh --install-dashboard \
  --dashboard-listen 0.0.0.0:9070 \
  --dashboard-auth-user operator \
  --dashboard-auth-password-file /root/mavlink-dashboard-password \
  --dashboard-api-token-file /root/mavlink-api-token
```

Record the exact reviewed tag/commit before updating and revalidate the
endpoint/config/profile-summary probes after the update. Do not treat the
newest upstream revision or `main` as a validated deployment automatically.

## Service Checks

```bash
sudo systemctl status mavlink-router
sudo journalctl -u mavlink-router -f

sudo systemctl status mavlink-anywhere-dashboard
sudo journalctl -u mavlink-anywhere-dashboard -f
```

Check the effective router configuration:

```bash
sudo sed -n '1,220p' /etc/mavlink-router/main.conf
```

## PixEagle Safety Notes

- Validate routing in SITL or on the bench before field use.
- Remove propellers for hardware setup and command-path tests.
- Keep a trained operator with a manual abort path available before enabling
  Offboard control.
- Confirm PX4 Offboard, data-link, manual-control, geofence, position, and
  battery failsafes before claiming a route is flight-ready.
- Do not expose PixEagle backend, MAVLink2REST, or MavlinkAnywhere dashboard
  ports beyond trusted networks, VPN, or SSH tunnels.
- A successful health/status probe is not routing evidence. Required endpoint,
  config, and profile-summary probes must succeed before accepting a
  PixEagle/PX4 integration run.

## Related Docs

- [mavlink-router manual setup](mavlink-router.md)
- [Port configuration](port-configuration.md)
- [MAVLink2REST API reference](../03-protocols/mavlink2rest-api.md)
- [Connection troubleshooting](../07-troubleshooting/connection-issues.md)
