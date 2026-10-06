# 2026-10-06 — changing LAN interfaces and companion-only settings

## Phase and slice

4b.4d network compatibility and QGC companion operation.

## Change

The explicit `trusted_lan_legacy` lab profile now treats empty host/origin
lists as an address-agnostic trusted-LAN deployment. This supports a Pi whose
Wi-Fi address changes while its robot Ethernet address remains fixed. Session
authentication and scoped authorization remain required; `local_only` and
reviewed restrictive profiles retain exact boundaries.

The native configuration guard no longer treats a connected MAVLink router as
an aircraft. With no aircraft identity, following and aircraft commands remain
unavailable, while authenticated backend settings and supervised restart can be
used when their normal safety barriers are satisfied. QGC camera availability
also uses the authenticated companion session; aircraft association is not
needed for camera/video bench work.

## Verification

- Policy checks accepted `192.168.0.226`, `192.168.137.161`, and a hostname with
  empty trusted-LAN lists.
- The Pi was updated to `d52766a79`, restarted, and verified active on
  `192.168.137.161` and `192.168.0.226`.
- Authenticated video produced verified JPEG metadata/binary pairs on the new
  Wi-Fi address.
- Native configuration tests passed except the workstation lacks the optional
  `httpx/httpx2` test dependency; the failing test was dependency collection,
  not a product assertion.

## Next step

Build the QGC companion-camera availability change, then test QGC against the
Wi-Fi address without a browser dashboard or PX4 connection. Following remains
gated until a real aircraft is verified.
