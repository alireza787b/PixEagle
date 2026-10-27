"""Session-only follower controls shared by browser and native clients."""

import math

from classes.api_v1_actions import ensure_api_action_store, new_api_action_record
from classes.api_v1_native_targets import NativeTargetError
from classes.api_v1_paths import API_V1_ACTION_FOLLOWING_CONTROL_PATH
from classes.runtime_identity import INSTANCE_ID, RUNTIME_ID


def session_control_snapshot(app, principal) -> list:
    concrete = getattr(getattr(app, 'follower', None), 'follower', None)
    getter = getattr(concrete, 'session_controls', None)
    if not callable(getter) or not getattr(app, 'following_active', False):
        return []
    continuity = app.get_target_continuity_status()
    state = continuity.get('authority_state')
    reason = None
    if getattr(app, '_following_stopping', False):
        reason = 'following_stopping'
    elif 'actions:execute' not in principal.scopes:
        reason = 'following_permission_required'
    elif state not in {'ACTIVE', 'COASTING', 'REACQUIRING'}:
        reason = 'following_authority_unavailable'
    if not app._is_command_preview_session():
        px4 = app.px4_interface
        identity = px4.get_aircraft_identity()
        if (not px4.is_command_connection_ready(require_fresh_telemetry=True)
                or identity.get('autopilot_uid') != app._following_session_aircraft_uid
                or identity.get('connection_generation') != app._following_session_connection_generation):
            reason = 'following_aircraft_unavailable'
        manager = getattr(app, 'mavlink_data_manager', None)
        flight = manager.get_flight_state() if manager is not None else {}
        if (flight.get('fresh') is not True
                or flight.get('autopilot_uid') != app._following_session_aircraft_uid
                or type(flight.get('flight_mode')) is not int
                or flight['flight_mode'] != getattr(manager, 'offboard_mode_code', None)):
            reason = 'following_authority_unavailable'
        from classes.circuit_breaker import FollowerCircuitBreaker
        if FollowerCircuitBreaker.is_active():
            reason = 'circuit_breaker_active'
    submitted = getattr(concrete, '_submitted_command_fields', None)
    effective = (math.sqrt(sum(submitted[name] ** 2 for name in
                              ('vel_body_fwd', 'vel_body_right', 'vel_body_down')))
                 if submitted else None)
    increasing = reason is None and state == 'ACTIVE' and not continuity.get('target_transition_pending')
    result = []
    for control in getter():
        limiting = (getattr(concrete, '_vertical_limit_status', None)
                    or ('target_recovery' if not increasing and reason is None else reason))
        if limiting is None and control['control_id'] == 'requested_speed' and effective is not None:
            if effective > control['value'] + .001:
                limiting = 'slowing_down'
            elif effective < control['value'] - .001:
                limiting = 'guidance_limited'
        result.append(dict(control, available=reason is None, increase_allowed=increasing,
                           reason_code=reason, effective_command_magnitude=effective, limiting_reason=limiting))
    return result


async def set_following_control(owner, request, response, http_request):
    from classes.api_v1_native_following import _actor, _audit, _request_identity

    path = API_V1_ACTION_FOLLOWING_CONTROL_PATH
    action_type = 'following_control_set'
    try:
        principal = _actor(http_request, start=False)
        if request.native_context is not None or request.native_safety_context is not None:
            raise NativeTargetError('session_control_context_invalid', 'Use the current follow-session identity.', 422)
        if not request.dry_run and (not request.confirm or not request.idempotency_key):
            raise NativeTargetError('following_confirmation_required', 'Confirm the adjustment with an idempotency key.', 422)
        scope, digest = _request_identity(request, principal)
        store = ensure_api_action_store(owner)
        app = owner.app_controller

        async def execute():
            async with app._follower_state_lock:
                if not request.dry_run:
                    replay = store.lookup_idempotent_action(action_type, request.idempotency_key, scope=scope)
                    if replay:
                        if store.request_digests.get(replay['action_id']) != digest:
                            raise NativeTargetError('idempotency_conflict', 'This key belongs to another adjustment.')
                        response.status_code = 200
                        return replay
                if (request.instance_id != INSTANCE_ID or request.runtime_id != RUNTIME_ID
                        or not app.following_active or getattr(app, '_following_stopping', False)
                        or request.follow_session_id != app._following_session_id
                        or request.aircraft_uid != app._following_session_aircraft_uid
                        or request.connection_generation != app._following_session_connection_generation):
                    raise NativeTargetError('following_session_stale', 'Following changed. Refresh status.')
                controls = session_control_snapshot(app, principal)
                control = next((item for item in controls if item['control_id'] == request.control_id), None)
                if control is None:
                    raise NativeTargetError('session_control_unsupported', 'This follower does not support this control.')
                if not control['available']:
                    raise NativeTargetError(control['reason_code'], 'Speed adjustment is temporarily unavailable.')
                if request.value is not None and request.value > control['value'] and not control['increase_allowed']:
                    raise NativeTargetError('session_control_recovery_active', 'Wait for confirmed tracking before increasing speed.')
                concrete = app.follower.follower
                # Validate without mutating on dry-run, including optimistic concurrency.
                try:
                    concrete.validate_session_control(request.control_id, request.value, request.expected_revision)
                except ValueError as exc:
                    raise NativeTargetError(str(exc), 'Refresh the requested speed and its permitted range.') from exc
                if not _audit(owner, principal, path, 'validated', action_type):
                    raise NativeTargetError('audit_unavailable', 'Adjustment audit is unavailable.', 503)
                if not request.dry_run:
                    concrete.update_session_control(request.control_id, request.value, request.expected_revision)
                record = new_api_action_record(
                    action_type=action_type, request=request,
                    status_value='validated' if request.dry_run else 'success',
                    accepted=True, executed=not request.dry_run,
                    following_active_before=True, following_active_after=True,
                    result={'session_controls': session_control_snapshot(app, principal),
                            'follow_session_id': app._following_session_id},
                )
                record['audit_event']['actor'] = {'kind': principal.kind.value, 'subject': principal.subject}
                store.store_action_record(record, scope=scope, digest=digest)
                _audit(owner, principal, path, 'success', action_type)
                response.status_code = 200 if request.dry_run else 202
                return record

        return await app._run_on_flight_event_loop(execute)
    except NativeTargetError as exc:
        return owner._api_v1_error_response(status_code=exc.status_code, code=exc.code,
                                            detail=str(exc), path=path)
    except Exception:
        return owner._api_v1_error_response(status_code=503, code='following_control_unavailable',
                                            detail='Refresh following status before another adjustment.', path=path)
