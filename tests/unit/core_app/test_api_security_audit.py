"""Tests for durable PixEagle API security audit events."""

import json
from types import SimpleNamespace

import pytest

from classes.api_security_audit import (
    APISecurityAuditError,
    APISecurityAuditLogger,
    audit_failure_must_block,
    resolve_api_security_audit_logger_from_parameters,
)
from classes.api_security_types import (
    APIAuditPolicy,
    APIPrincipal,
    APISensitivity,
    STATUS_READ,
)


def _read_jsonl(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_security_audit_logger_writes_sanitized_jsonl_event(tmp_path):
    audit_path = tmp_path / "security_audit.jsonl"
    audit_logger = APISecurityAuditLogger(log_path=audit_path)
    principal = APIPrincipal.bearer(
        token_id="token-1",
        subject="ci-client",
        scopes={STATUS_READ},
    )

    recorded = audit_logger.record_event(
        event_type="api.http.authorization",
        outcome="allowed",
        reason="allowed",
        transport="http",
        method="GET",
        path="/api/v1/runtime/status",
        status_code=200,
        principal=principal,
        audit_policy=APIAuditPolicy.SENSITIVE_READ,
        sensitivity=APISensitivity.STATUS,
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        origin=None,
        request_id="request-1",
    )

    assert recorded is True
    events = _read_jsonl(audit_path)
    assert len(events) == 1
    assert events[0]["event_type"] == "api.http.authorization"
    assert events[0]["actor"] == {
        "kind": "bearer",
        "subject": "ci-client",
        "role": None,
        "credential_id": "token-1",
        "scopes": ["status:read"],
    }
    serialized = json.dumps(events[0])
    assert "secret-token" not in serialized
    assert "bearer secret" not in serialized.lower()


def test_security_audit_logger_skips_allowed_none_policy(tmp_path):
    audit_path = tmp_path / "security_audit.jsonl"
    audit_logger = APISecurityAuditLogger(log_path=audit_path)

    recorded = audit_logger.record_event(
        event_type="api.http.authorization",
        outcome="allowed",
        reason="allowed",
        transport="http",
        method="GET",
        path="/api/v1/auth/session",
        status_code=200,
        principal=APIPrincipal.anonymous(),
        audit_policy=APIAuditPolicy.NONE,
        sensitivity=APISensitivity.SYSTEM,
    )

    assert recorded is False
    assert not audit_path.exists()


def test_security_audit_logger_raises_when_path_is_not_writable(tmp_path):
    audit_logger = APISecurityAuditLogger(log_path=tmp_path)

    with pytest.raises(APISecurityAuditError):
        audit_logger.record_event(
            event_type="api.http.authorization",
            outcome="allowed",
            reason="allowed",
            transport="http",
            method="POST",
            path="/api/v1/actions/offboard-stop",
            status_code=200,
            principal=APIPrincipal.local_compat(),
            audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
            sensitivity=APISensitivity.CONTROL,
        )


def test_allowed_mutation_and_security_critical_audit_failures_block():
    assert audit_failure_must_block(
        audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
        outcome="allowed",
    )
    assert audit_failure_must_block(
        audit_policy=APIAuditPolicy.MUTATION,
        outcome="allowed",
    )
    assert not audit_failure_must_block(
        audit_policy=APIAuditPolicy.SENSITIVE_READ,
        outcome="allowed",
    )
    assert not audit_failure_must_block(
        audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
        outcome="denied",
    )


def test_resolve_security_audit_logger_from_parameters(tmp_path):
    audit_path = tmp_path / "security.jsonl"
    parameters = SimpleNamespace(
        _raw_config={
            "Streaming": {
                "API_SECURITY_AUDIT_ENABLED": True,
                "API_SECURITY_AUDIT_LOG_PATH": str(audit_path),
                "API_SECURITY_AUDIT_MAX_BYTES": 4096,
                "API_SECURITY_AUDIT_BACKUP_COUNT": 2,
            }
        }
    )

    audit_logger = resolve_api_security_audit_logger_from_parameters(parameters)

    assert audit_logger.enabled is True
    assert audit_logger.log_path == audit_path
    assert audit_logger.max_bytes == 4096
    assert audit_logger.backup_count == 2
