"""Contract tests for the declarative PixEagle API security policy."""

import pytest

from classes.api_security_policy import (
    API_ROUTE_SECURITY_RULES,
    DENY_UNCLASSIFIED,
    matching_route_security_rules,
    resolve_route_security_policy,
)
from classes.api_security_types import (
    ACTIONS_EXECUTE,
    ALL_API_SCOPES,
    APIAccessMode,
    APIAuditPolicy,
    APIPrincipal,
    APIPrincipalKind,
    APISensitivity,
    CONFIG_WRITE,
    CONTROL_WRITE,
    DEBUG_READ,
    MEDIA_READ,
    MODELS_MANAGE,
    RUNTIME_REPORT,
    SAFETY_WRITE,
    SITL_INJECT,
    STATUS_READ,
    SYSTEM_ADMIN,
    authorize_api_request,
)
from tests.test_api_route_inventory import EXPECTED_ROUTES


IMPLICIT_FASTAPI_ROUTES = {
    (method, path)
    for method in ("GET", "HEAD")
    for path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc")
}


def test_every_declared_route_has_exactly_one_security_rule():
    problems = {
        (method, path): [rule.name for rule in matching_route_security_rules(method, path)]
        for method, path in EXPECTED_ROUTES
        if len(matching_route_security_rules(method, path)) != 1
    }

    assert problems == {}


def test_policy_surface_exactly_matches_declared_and_implicit_routes():
    policy_pairs = {
        (method, path)
        for rule in API_ROUTE_SECURITY_RULES
        for method in rule.methods
        for path in rule.path_templates
    }

    assert policy_pairs == EXPECTED_ROUTES | IMPLICIT_FASTAPI_ROUTES


def test_implicit_fastapi_routes_are_local_admin_only():
    for method, path in IMPLICIT_FASTAPI_ROUTES:
        matches = matching_route_security_rules(method, path)
        assert [rule.name for rule in matches] == ["local_api_documentation"]
        assert matches[0].policy.access == APIAccessMode.LOCAL_ONLY
        assert matches[0].policy.required_scopes == frozenset({SYSTEM_ADMIN})


def test_security_rules_are_structurally_valid_and_unambiguous():
    names = [rule.name for rule in API_ROUTE_SECURITY_RULES]
    assert len(names) == len(set(names))

    for rule in API_ROUTE_SECURITY_RULES:
        assert rule.methods
        assert rule.methods == frozenset(method.upper() for method in rule.methods)
        assert rule.path_templates
        assert all(path.startswith("/") for path in rule.path_templates)
        assert rule.policy.required_scopes <= ALL_API_SCOPES
        assert rule.policy.rationale.strip()


def test_unknown_or_wrong_method_routes_fail_closed():
    assert resolve_route_security_policy("GET", "/api/not-classified") is DENY_UNCLASSIFIED
    assert resolve_route_security_policy("PATCH", "/status") is DENY_UNCLASSIFIED
    assert resolve_route_security_policy("POST", "/docs") is DENY_UNCLASSIFIED


def test_auth_routes_have_explicit_bootstrap_and_logout_policy():
    session_status = resolve_route_security_policy("GET", "/api/v1/auth/session")
    login = resolve_route_security_policy("POST", "/api/v1/auth/login")
    logout = resolve_route_security_policy("POST", "/api/v1/auth/logout")

    assert session_status.access == APIAccessMode.PUBLIC
    assert login.access == APIAccessMode.PUBLIC
    assert login.audit == APIAuditPolicy.SECURITY_CRITICAL
    assert logout.access == APIAccessMode.AUTHENTICATED
    assert logout.csrf_required_for_session is True
    assert logout.audit == APIAuditPolicy.SECURITY_CRITICAL


@pytest.mark.parametrize(
    ("method", "path", "expected_rule"),
    [
        ("GET", "/api/models/model-1/file", "model_reads"),
        ("DELETE", "/api/models/model-1", "model_delete_mutations"),
        ("PUT", "/api/config/Streaming/HTTP_STREAM_HOST", "config_parameter_mutations"),
        ("GET", "/api/safety/limits/mc_velocity_position", "safety_reads"),
        ("WEBSOCKET", "/ws/video_feed?client=test", "media_websocket_reads"),
    ],
)
def test_concrete_paths_resolve_against_templates(method, path, expected_rule):
    matches = matching_route_security_rules(method, path)
    assert [rule.name for rule in matches] == [expected_rule]


def test_write_scopes_require_csrf_for_sessions_and_mutation_audit():
    mutation_scopes = {
        CONFIG_WRITE,
        CONTROL_WRITE,
        SAFETY_WRITE,
        ACTIONS_EXECUTE,
        SYSTEM_ADMIN,
        SITL_INJECT,
        MODELS_MANAGE,
        RUNTIME_REPORT,
    }
    for rule in API_ROUTE_SECURITY_RULES:
        if not rule.methods.intersection({"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if not rule.policy.required_scopes.intersection(mutation_scopes):
            continue
        assert rule.policy.csrf_required_for_session is True, rule.name
        assert rule.policy.audit in {
            APIAuditPolicy.MUTATION,
            APIAuditPolicy.SECURITY_CRITICAL,
        }, rule.name


def test_media_and_legacy_surfaces_keep_their_intended_boundaries():
    for method, path in (
        ("GET", "/video_feed"),
        ("GET", "/api/v1/streams/media-health"),
        ("WEBSOCKET", "/ws/video_feed"),
        ("WEBSOCKET", "/ws/webrtc_signaling"),
    ):
        policy = resolve_route_security_policy(method, path)
        assert policy.access == APIAccessMode.AUTHENTICATED
        assert policy.sensitivity == APISensitivity.MEDIA
        assert policy.required_scopes == frozenset({MEDIA_READ})

    for method, path in (
        ("GET", "/api/yolo/models"),
        ("POST", "/api/yolo/upload"),
        ("POST", "/api/v1/sitl/injections/video-stall"),
    ):
        assert resolve_route_security_policy(method, path).access == APIAccessMode.LOCAL_ONLY

    for path in (
        "/commands/start_tracking",
        "/commands/stop_tracking",
        "/commands/redetect",
        "/commands/toggle_segmentation",
        "/commands/toggle_smart_mode",
        "/commands/smart_click",
    ):
        assert resolve_route_security_policy("POST", path) is DENY_UNCLASSIFIED


def test_media_health_rejects_status_only_bearer_scope():
    policy = resolve_route_security_policy("GET", "/api/v1/streams/media-health")
    principal = APIPrincipal.bearer(
        token_id="status-only-token",
        subject="status-agent",
        scopes={STATUS_READ},
    )

    decision = authorize_api_request(
        policy=policy,
        principal=principal,
        is_loopback_client=False,
    )

    assert policy.sensitivity == APISensitivity.MEDIA
    assert policy.required_scopes == frozenset({MEDIA_READ})
    assert decision.allowed is False
    assert decision.reason == "insufficient_scope"
    assert decision.missing_scopes == (MEDIA_READ,)


def test_runtime_log_reads_require_debug_scope():
    policies = [
        resolve_route_security_policy("GET", "/api/v1/logs/status"),
        resolve_route_security_policy("GET", "/api/v1/logs/sessions/demo_run"),
        resolve_route_security_policy(
            "GET",
            "/api/v1/logs/sessions/demo_run/export",
        ),
    ]

    for policy in policies:
        viewer = authorize_api_request(
            policy=policy,
            principal=APIPrincipal.session(
                username="viewer-1",
                role="viewer",
                session_id="session-viewer-1",
            ),
            is_loopback_client=False,
        )
        admin = authorize_api_request(
            policy=policy,
            principal=APIPrincipal.session(
                username="admin-1",
                role="admin",
                session_id="session-admin-1",
            ),
            is_loopback_client=False,
        )

        assert policy.sensitivity == APISensitivity.DEBUG
        assert policy.required_scopes == frozenset({DEBUG_READ})
        assert viewer.allowed is False
        assert viewer.reason == "insufficient_scope"
        assert viewer.missing_scopes == (DEBUG_READ,)
        assert admin.allowed is True


def test_frontend_error_reports_require_runtime_report_scope_and_csrf():
    policy = resolve_route_security_policy("POST", "/api/v1/logs/frontend-errors")

    viewer = APIPrincipal.session(
        username="viewer-1",
        role="viewer",
        session_id="session-viewer-1",
    )
    status_only = APIPrincipal.bearer(
        token_id="status-token",
        subject="status-agent",
        scopes={STATUS_READ},
    )

    missing_csrf = authorize_api_request(
        policy=policy,
        principal=viewer,
        is_loopback_client=False,
    )
    allowed = authorize_api_request(
        policy=policy,
        principal=viewer,
        is_loopback_client=False,
        csrf_valid=True,
    )
    insufficient = authorize_api_request(
        policy=policy,
        principal=status_only,
        is_loopback_client=False,
    )

    assert policy.sensitivity == APISensitivity.DEBUG
    assert policy.audit == APIAuditPolicy.MUTATION
    assert policy.csrf_required_for_session is True
    assert policy.required_scopes == frozenset({RUNTIME_REPORT})
    assert missing_csrf.allowed is False
    assert missing_csrf.reason == "csrf_required"
    assert allowed.allowed is True
    assert insufficient.allowed is False
    assert insufficient.missing_scopes == (RUNTIME_REPORT,)


def test_anonymous_and_insufficient_scope_requests_are_denied():
    policy = resolve_route_security_policy("POST", "/api/v1/actions/tracker-restart")

    anonymous = authorize_api_request(
        policy=policy,
        principal=APIPrincipal.anonymous(),
        is_loopback_client=True,
    )
    assert anonymous.allowed is False
    assert anonymous.reason == "authentication_required"

    viewer = authorize_api_request(
        policy=policy,
        principal=APIPrincipal.session(
            username="viewer-1",
            role="viewer",
            session_id="session-viewer-1",
        ),
        is_loopback_client=True,
        csrf_valid=True,
    )
    assert viewer.allowed is False
    assert viewer.reason == "insufficient_scope"
    assert viewer.missing_scopes == (ACTIONS_EXECUTE,)


def test_session_roles_are_least_privilege_and_csrf_is_session_bound():
    control_policy = resolve_route_security_policy(
        "POST",
        "/api/v1/actions/tracker-restart",
    )
    operator = APIPrincipal.session(
        username="operator-1",
        role="operator",
        session_id="session-operator-1",
    )
    viewer = APIPrincipal.session(
        username="viewer-1",
        role="viewer",
        session_id="session-viewer-1",
    )

    missing_csrf = authorize_api_request(
        policy=control_policy,
        principal=operator,
        is_loopback_client=False,
    )
    assert missing_csrf.reason == "csrf_required"

    allowed = authorize_api_request(
        policy=control_policy,
        principal=operator,
        is_loopback_client=False,
        csrf_valid=True,
    )
    assert allowed.allowed is True

    for method, path, missing_scope in (
        ("PUT", "/api/config/Streaming", CONFIG_WRITE),
        ("POST", "/api/models/upload", MODELS_MANAGE),
        ("POST", "/api/circuit-breaker/toggle", SAFETY_WRITE),
        ("POST", "/api/system/restart", SYSTEM_ADMIN),
        ("POST", "/api/v1/sitl/injections/video-stall", SITL_INJECT),
    ):
        decision = authorize_api_request(
            policy=resolve_route_security_policy(method, path),
            principal=operator,
            is_loopback_client=True,
            csrf_valid=True,
        )
        assert decision.reason == "insufficient_scope"
        assert decision.missing_scopes == (missing_scope,)

    viewer_config = authorize_api_request(
        policy=resolve_route_security_policy("GET", "/api/config/current"),
        principal=viewer,
        is_loopback_client=True,
    )
    assert viewer_config.reason == "insufficient_scope"
    assert viewer_config.missing_scopes == ("config:read",)


def test_bearer_scopes_are_exact_and_do_not_expand_into_roles():
    principal = APIPrincipal.bearer(
        token_id="token-1",
        subject="automation-1",
        scopes={ACTIONS_EXECUTE},
    )
    control = authorize_api_request(
        policy=resolve_route_security_policy(
            "POST",
            "/api/v1/actions/tracker-restart",
        ),
        principal=principal,
        is_loopback_client=False,
    )
    config = authorize_api_request(
        policy=resolve_route_security_policy("PUT", "/api/config/Streaming"),
        principal=principal,
        is_loopback_client=False,
    )

    assert control.allowed is True
    assert config.reason == "insufficient_scope"
    assert config.missing_scopes == (CONFIG_WRITE,)
    assert principal.role is None


def test_local_only_routes_require_loopback_even_for_admin_or_compat_principals():
    policy = resolve_route_security_policy("POST", "/api/system/restart")
    admin = APIPrincipal.session(
        username="admin-1",
        role="admin",
        session_id="session-admin-1",
    )

    remote_admin = authorize_api_request(
        policy=policy,
        principal=admin,
        is_loopback_client=False,
        csrf_valid=True,
    )
    assert remote_admin.reason == "route_is_local_only"

    local_admin = authorize_api_request(
        policy=policy,
        principal=admin,
        is_loopback_client=True,
        csrf_valid=True,
    )
    assert local_admin.allowed is True

    remote_compat = authorize_api_request(
        policy=resolve_route_security_policy("GET", "/status"),
        principal=APIPrincipal.local_compat(),
        is_loopback_client=False,
    )
    assert remote_compat.reason == "local_compat_requires_loopback"


def test_principal_factories_reject_ambiguous_or_unknown_identity_data():
    with pytest.raises(ValueError, match="username"):
        APIPrincipal.session(username=" ", role="viewer", session_id="session-1")
    with pytest.raises(ValueError, match="Session ID"):
        APIPrincipal.session(username="viewer-1", role="viewer", session_id="")
    with pytest.raises(ValueError, match="role"):
        APIPrincipal.session(
            username="operator-1",
            role="superuser",
            session_id="session-1",
        )
    with pytest.raises(ValueError, match="token ID"):
        APIPrincipal.bearer(token_id="", scopes={CONTROL_WRITE})
    with pytest.raises(ValueError, match="subject"):
        APIPrincipal.bearer(token_id="token-1", subject="", scopes={CONTROL_WRITE})
    with pytest.raises(ValueError, match="Unsupported bearer scopes"):
        APIPrincipal.bearer(token_id="token-1", scopes={"flight:everything"})
    with pytest.raises(ValueError, match="Session scopes"):
        APIPrincipal(
            kind=APIPrincipalKind.SESSION,
            subject="viewer-1",
            role="viewer",
            credential_id="session-1",
            scopes=ALL_API_SCOPES,
        )
