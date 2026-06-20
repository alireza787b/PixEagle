# Production Remote Reverse-Proxy Runbook

This runbook completes the operator-managed part of the guarded
`production_remote` setup profile. The profile generates PixEagle configuration
and credentials; it does not install TLS, a reverse proxy, firewall rules, or a
service.

## Preconditions

- Run the profile on the Linux deployment host. Production credential
  generation currently relies on POSIX owner-only file modes; Windows ACL
  automation is not yet evidence-backed.
- Know the OS account that runs PixEagle. That account must own and read the
  browser-session user file.
- Have a browser-trusted public certificate, internal PKI certificate, or other
  reviewed TLS trust anchor for the exact public host.
- Keep dashboard `3040` and backend `5077` bound to loopback.

Create a private deployment directory as the PixEagle service user:

```bash
install -d -m 0700 "$HOME/.config/pixeagle/secrets"
```

Generate the profile without placing the password in captured stdout:

```bash
make production-remote-profile \
  PUBLIC_HOST=pixeagle.example \
  SESSION_USER_FILE="$HOME/.config/pixeagle/secrets/browser-users.json" \
  CREDENTIAL_HANDOFF_FILE="$HOME/.config/pixeagle/secrets/initial-credentials.json"
```

For a non-standard public HTTPS port, also set
`PUBLIC_ORIGIN=https://pixeagle.example:8443`. The generated
`API_ALLOWED_HOSTS` authority includes that exact port.

Both generated credential files are owner-only on POSIX. Transfer the initial
credential through the approved secret channel, verify login, and delete
`initial-credentials.json`. Rotation refuses to overwrite either file unless
`ROTATE_SESSION_CREDENTIALS=1` is explicit. It backs up the hashed runtime user
file and config, but atomically replaces the plaintext handoff without archiving
the old password.

## Nginx Reference Shape

This is a reference, not an installer. Adapt certificate paths, host, TLS
policy, log destinations, and allowed client networks to the deployment:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl http2;
    server_name pixeagle.example;

    ssl_certificate     /etc/ssl/pixeagle/fullchain.pem;
    ssl_certificate_key /etc/ssl/pixeagle/private.key;

    location = /pixeagle {
        return 308 /pixeagle/;
    }

    location /pixeagle/ {
        proxy_pass http://127.0.0.1:3040/;
        proxy_set_header Host $http_host;
    }

    location /pixeagle-api/ {
        proxy_pass http://127.0.0.1:5077/;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header Origin $http_origin;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

The trailing slash on each `proxy_pass` removes the public prefix before the
request reaches PixEagle. The checked-in dashboard production build uses
relative asset URLs, so JavaScript, CSS, icons, and the manifest stay under
`/pixeagle/`. Router links are basename-aware. Preserve the reviewed external
Host authority and browser Origin. Do not publish a second direct route to
`5077`.

## Local Browser Evidence Harness

Before target-host deployment, validate the checked-in evidence plan:

```bash
make production-remote-browser-e2e-dry-run
```

Install the pinned Playwright Chromium once on a new development host. This is
an explicit opt-in because Playwright may install Linux browser dependencies:

```bash
make production-remote-browser-install
```

Execute it only after explicitly accepting the ephemeral self-signed TLS
boundary:

```bash
ALLOW_LOCAL_SELF_SIGNED_TLS=1 make production-remote-browser-e2e
```

The execute target rebuilds the dashboard, generates a temporary
`production_remote` profile and credentials, starts separate loopback backend
and HTTPS reverse-proxy servers inside one harness process, maps
`pixeagle.test` to loopback in Chromium, and runs Playwright. It uses
PixEagle's real Host/Origin middleware, auth runtime, CSRF policy, security
audit, and video WebSocket handler. JPEG and action responses are inert
fixtures; no camera, tracker, follower, MAVSDK, PX4, or aircraft process
starts.

Local artifacts are written under `reports/production-remote-browser/`. They
include version/source hashes, effective security settings without
credentials, request authority/path metadata, screenshots, a raw sanitized
security-audit log, and a retained-artifact secret scan. The `upload/`
subdirectory is a fixed allowlist that excludes raw process logs and raw audit
events; the manual workflow uploads only that subdirectory.
The harness does not retain plaintext credentials, cookie or CSRF values, TLS
private keys, HAR files, traces, or videos.

The harness uses a Python ASGI proxy and Playwright
`ignoreHTTPSErrors` for explicitly local self-signed TLS. A pass proves the
checked-in application boundary and documented path shape on that checkout. It
does not prove nginx/Caddy configuration, browser PKI trust, target service
ownership, firewall rules, external reachability, or production handoff. The
manual `Production Remote Browser E2E` GitHub Actions workflow runs the same
application-boundary evidence with Playwright-managed Chromium. Local runs
also use Playwright-managed Chromium by default; an explicit
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` may select a reviewed system browser.

## Firewall Boundary

Expose only the reverse proxy's TLS listener to the intended client network:

```bash
sudo ufw allow from <trusted-cidr> to any port 443 proto tcp
```

Use the configured TLS port instead of `443` when `PUBLIC_ORIGIN` has a custom
port. Do not open `3040` or `5077` for this profile. QGC UDP video and MAVLink
ports are separate deployment decisions.

## Evidence Checklist

Record exact versions, config paths, commands, timestamps, and sanitized logs.
At minimum verify:

1. `ss -ltnp` shows `3040` and `5077` only on loopback and the proxy on the
   intended TLS interface.
2. The browser loads `/pixeagle/` through a trusted HTTPS connection.
3. Unauthenticated API, MJPEG, WebSocket, and WebRTC requests fail closed.
4. Login establishes the Secure HttpOnly session; logout and expiry deny media
   in existing tabs and close already-open MJPEG, video WebSocket, and WebRTC
   signaling/peer sessions.
5. Viewer accounts can read media but cannot execute actions.
6. Wrong Host, wrong Origin, cross-site, missing-CSRF, expired-cookie, and
   unrelated authority-port requests are rejected.
7. MJPEG, WebSocket, and WebRTC traverse `/pixeagle-api/` without exposing
   backend port `5077`.
8. Security-audit records contain the expected allowed/denied events without
   passwords, cookies, bearer tokens, or query credentials.
9. Firewall tests from an untrusted client cannot reach `3040`, `5077`,
   MAVLink2REST, or local MAVLink endpoints.

Store deployment evidence outside the repository if it contains hostnames,
network topology, certificates, credentials, or operator identity.

## Rollback

Stop the reverse proxy before changing the public boundary. Restore the
timestamped `configs/config.yaml.backup.*` and credential backup only after
verifying ownership and mode, or reapply `local_dev`. Remove the public TLS
firewall rule and confirm `3040`/`5077` remain loopback before restarting
PixEagle.
