# Native circuit-breaker status

The QGroundControl PixEagle Options dialog and the web Dashboard control the
same `FOLLOWER_CIRCUIT_BREAKER` backend setting. The QGC control is available
only when the integration context advertises `safety.circuit_breaker.v1` and
the principal has `safety:read`. Older backends remain read-only in QGC.

`GET /api/v1/integration/safety` returns a no-store, typed snapshot with
`instance_id`, `runtime_id`, `state_generation`, observed `active` and
`persisted_active` values, `available`, `can_set`, `follower_test`,
`following_active`, and a reason code. An unknown, inconsistent or stale
snapshot is not evidence that flight commands are blocked.

To change the setting, a client sends the existing confirmed and idempotent
`POST /api/v1/actions/circuit-breaker-set` action with `enabled` and a
`native_safety_context` copied from its fresh snapshot:

```json
{
  "instance_id": "captured-instance",
  "runtime_id": "captured-runtime",
  "state_generation": "captured-generation",
  "expected_active": true
}
```

The action requires `safety:write`, CSRF for a browser session, an idempotency
key, `confirm: true`, and a matching current snapshot. QGC requires a separate
operator confirmation before setting `enabled: false`. The backend rejects any
change while following is active and rejects permitting aircraft commands while
Follower Test is configured. Clients refresh the
authoritative state after success, conflict or unknown outcome and never replay
a local switch value after reconnect.

The circuit breaker governs PixEagle aircraft-command dispatch. It does not
stop the camera, kill an aircraft, or inhibit ordinary QGC flight controls.
Follower Test is command preview; an active test must not be labelled aircraft
following. Camera Stop remains available independently of this setting.
