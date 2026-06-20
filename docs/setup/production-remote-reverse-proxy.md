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
   in existing tabs.
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
