# Stock MAVLink ownership

The standard UART replacement now has source-owned physical pose, aircraft
parameter derivation, stable Start contexts and shared session speed/Restore.
One-shot MavlinkDirect replaces autonomous SDK resend in the component candidate;
the existing commander remains the only publication scheduler. A stopped sender
allows native Offboard-loss behavior instead of indefinitely renewing old intent.

Stock airplane SIH confirms speed editing, steep descent, Restore and Hold through
the production owner/commander. The received-bearing adapter preserves original
camera/attitude receipts without inventing source timestamps or reset evidence.
The shared FW supervisor retains its eight-second loss/retarget deadline.

The [checkpoint](../checkpoints/2026-11-16-stock-mavlink-session-ownership.md)
records evidence, verification and latest requested public/private configuration
values. Full application/client and VTOL qualification remain next. Hardware and
saved profiles were not changed; this is not flight clearance or a final release.
