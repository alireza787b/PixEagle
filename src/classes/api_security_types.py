"""Typed principals, scopes, and authorization decisions for PixEagle APIs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping, Optional


class APIAccessMode(str, Enum):
    """How a route may be reached once authentication enforcement is enabled."""

    AUTHENTICATED = "authenticated"
    LOCAL_ONLY = "local_only"
    DENY = "deny"


class APIPrincipalKind(str, Enum):
    """Credential source for an authenticated request."""

    ANONYMOUS = "anonymous"
    LOCAL_COMPAT = "local_compat"
    SESSION = "session"
    BEARER = "bearer"


class APIAuditPolicy(str, Enum):
    """Minimum audit treatment expected for a route."""

    NONE = "none"
    SENSITIVE_READ = "sensitive_read"
    MUTATION = "mutation"
    SECURITY_CRITICAL = "security_critical"


class APISensitivity(str, Enum):
    """High-level data or control domain exposed by a route."""

    STATUS = "status"
    TELEMETRY = "telemetry"
    MEDIA = "media"
    CONFIG = "config"
    MODELS = "models"
    RECORDINGS = "recordings"
    CONTROL = "control"
    SAFETY = "safety"
    SYSTEM = "system"
    VALIDATION = "validation"
    DEBUG = "debug"
    UNKNOWN = "unknown"


STATUS_READ = "status:read"
TELEMETRY_READ = "telemetry:read"
MEDIA_READ = "media:read"
MEDIA_WRITE = "media:write"
CONFIG_READ = "config:read"
CONFIG_WRITE = "config:write"
MODELS_READ = "models:read"
MODELS_SELECT = "models:select"
MODELS_MANAGE = "models:manage"
RECORDINGS_READ = "recordings:read"
RECORDINGS_WRITE = "recordings:write"
CONTROL_READ = "control:read"
CONTROL_WRITE = "control:write"
SAFETY_READ = "safety:read"
SAFETY_WRITE = "safety:write"
ACTIONS_READ = "actions:read"
ACTIONS_EXECUTE = "actions:execute"
SYSTEM_READ = "system:read"
SYSTEM_ADMIN = "system:admin"
SITL_INJECT = "sitl:inject"
DEBUG_READ = "debug:read"

ALL_API_SCOPES = frozenset(
    {
        STATUS_READ,
        TELEMETRY_READ,
        MEDIA_READ,
        MEDIA_WRITE,
        CONFIG_READ,
        CONFIG_WRITE,
        MODELS_READ,
        MODELS_SELECT,
        MODELS_MANAGE,
        RECORDINGS_READ,
        RECORDINGS_WRITE,
        CONTROL_READ,
        CONTROL_WRITE,
        SAFETY_READ,
        SAFETY_WRITE,
        ACTIONS_READ,
        ACTIONS_EXECUTE,
        SYSTEM_READ,
        SYSTEM_ADMIN,
        SITL_INJECT,
        DEBUG_READ,
    }
)

ROLE_SCOPES: Mapping[str, frozenset[str]] = MappingProxyType({
    "viewer": frozenset(
        {
            STATUS_READ,
            TELEMETRY_READ,
            MEDIA_READ,
            MODELS_READ,
            RECORDINGS_READ,
            CONTROL_READ,
            SAFETY_READ,
            ACTIONS_READ,
            SYSTEM_READ,
        }
    ),
    "operator": frozenset(
        {
            STATUS_READ,
            TELEMETRY_READ,
            MEDIA_READ,
            MEDIA_WRITE,
            CONFIG_READ,
            MODELS_READ,
            MODELS_SELECT,
            RECORDINGS_READ,
            RECORDINGS_WRITE,
            CONTROL_READ,
            CONTROL_WRITE,
            SAFETY_READ,
            ACTIONS_READ,
            ACTIONS_EXECUTE,
            SYSTEM_READ,
        }
    ),
    "admin": ALL_API_SCOPES,
})


@dataclass(frozen=True)
class APIPrincipal:
    """Authenticated actor context used by the policy decision engine."""

    kind: APIPrincipalKind
    subject: str
    scopes: frozenset[str] = frozenset()
    role: Optional[str] = None
    credential_id: Optional[str] = None

    def __post_init__(self) -> None:
        try:
            normalized_kind = APIPrincipalKind(self.kind)
        except ValueError as exc:
            raise ValueError(f"Unsupported principal kind: {self.kind!r}") from exc

        normalized_subject = str(self.subject or "").strip()
        normalized_role = str(self.role).strip().lower() if self.role is not None else None
        normalized_credential_id = (
            str(self.credential_id).strip()
            if self.credential_id is not None
            else None
        )
        normalized_scopes = frozenset(
            str(scope).strip().lower()
            for scope in self.scopes
            if str(scope).strip()
        )
        unknown = normalized_scopes - ALL_API_SCOPES

        if not normalized_subject:
            raise ValueError("Principal subject must not be empty")
        if unknown:
            raise ValueError(f"Unsupported principal scopes: {sorted(unknown)}")

        object.__setattr__(self, "kind", normalized_kind)
        object.__setattr__(self, "subject", normalized_subject)
        object.__setattr__(self, "role", normalized_role)
        object.__setattr__(self, "credential_id", normalized_credential_id)
        object.__setattr__(self, "scopes", normalized_scopes)

        if normalized_kind == APIPrincipalKind.ANONYMOUS:
            if normalized_scopes or normalized_role or normalized_credential_id:
                raise ValueError("Anonymous principals cannot carry credentials or scopes")
            return

        if normalized_kind == APIPrincipalKind.LOCAL_COMPAT:
            if normalized_role or normalized_credential_id:
                raise ValueError("Local compatibility principals cannot carry credentials")
            if normalized_scopes != ALL_API_SCOPES:
                raise ValueError("Local compatibility principals require the fixed scope set")
            return

        if normalized_kind == APIPrincipalKind.SESSION:
            if normalized_role not in ROLE_SCOPES:
                raise ValueError(f"Unsupported session role: {self.role!r}")
            if normalized_scopes != ROLE_SCOPES[normalized_role]:
                raise ValueError("Session scopes must match the declared role")
            if not normalized_credential_id:
                raise ValueError("Session ID must not be empty")
            return

        if normalized_role is not None:
            raise ValueError("Bearer principals cannot inherit a session role")
        if not normalized_credential_id:
            raise ValueError("Bearer token ID must not be empty")

    @classmethod
    def anonymous(cls) -> "APIPrincipal":
        return cls(kind=APIPrincipalKind.ANONYMOUS, subject="anonymous")

    @classmethod
    def local_compat(cls) -> "APIPrincipal":
        return cls(
            kind=APIPrincipalKind.LOCAL_COMPAT,
            subject="local-auth-disabled",
            scopes=ALL_API_SCOPES,
        )

    @classmethod
    def session(
        cls,
        *,
        username: str,
        role: str,
        session_id: str,
    ) -> "APIPrincipal":
        normalized_username = str(username or "").strip()
        if not normalized_username:
            raise ValueError("Session username must not be empty")
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            raise ValueError("Session ID must not be empty")
        normalized_role = str(role or "").strip().lower()
        if normalized_role not in ROLE_SCOPES:
            raise ValueError(f"Unsupported session role: {role!r}")
        return cls(
            kind=APIPrincipalKind.SESSION,
            subject=normalized_username,
            role=normalized_role,
            credential_id=normalized_session_id,
            scopes=ROLE_SCOPES[normalized_role],
        )

    @classmethod
    def bearer(
        cls,
        *,
        token_id: str,
        scopes: Iterable[str],
        subject: str = "machine-client",
    ) -> "APIPrincipal":
        normalized_token_id = str(token_id or "").strip()
        if not normalized_token_id:
            raise ValueError("Bearer token ID must not be empty")
        normalized_subject = str(subject or "").strip()
        if not normalized_subject:
            raise ValueError("Bearer subject must not be empty")
        normalized_scopes = frozenset(
            str(scope).strip().lower() for scope in scopes if str(scope).strip()
        )
        unknown = normalized_scopes - ALL_API_SCOPES
        if unknown:
            raise ValueError(f"Unsupported bearer scopes: {sorted(unknown)}")
        return cls(
            kind=APIPrincipalKind.BEARER,
            subject=normalized_subject,
            credential_id=normalized_token_id,
            scopes=normalized_scopes,
        )


@dataclass(frozen=True)
class APIRouteSecurityPolicy:
    """Authorization and audit requirements for one route family."""

    access: APIAccessMode
    sensitivity: APISensitivity
    required_scopes: frozenset[str]
    audit: APIAuditPolicy
    csrf_required_for_session: bool = False
    rationale: str = ""


@dataclass(frozen=True)
class APIAuthorizationDecision:
    """Policy decision returned without exposing credential material."""

    allowed: bool
    reason: str
    missing_scopes: tuple[str, ...] = ()


def authorize_api_request(
    *,
    policy: APIRouteSecurityPolicy,
    principal: APIPrincipal,
    is_loopback_client: bool,
    csrf_valid: bool = False,
) -> APIAuthorizationDecision:
    """Evaluate route policy without reading credentials or mutating state."""
    if policy.access == APIAccessMode.DENY:
        return APIAuthorizationDecision(False, "route_policy_denied")

    if policy.access == APIAccessMode.LOCAL_ONLY and not is_loopback_client:
        return APIAuthorizationDecision(False, "route_is_local_only")

    if (
        principal.kind == APIPrincipalKind.LOCAL_COMPAT
        and not is_loopback_client
    ):
        return APIAuthorizationDecision(False, "local_compat_requires_loopback")

    if principal.kind == APIPrincipalKind.ANONYMOUS:
        return APIAuthorizationDecision(False, "authentication_required")

    missing = tuple(sorted(policy.required_scopes - principal.scopes))
    if missing:
        return APIAuthorizationDecision(
            False,
            "insufficient_scope",
            missing_scopes=missing,
        )

    if (
        policy.csrf_required_for_session
        and principal.kind == APIPrincipalKind.SESSION
        and not csrf_valid
    ):
        return APIAuthorizationDecision(False, "csrf_required")

    return APIAuthorizationDecision(True, "allowed")


__all__ = [
    "ACTIONS_EXECUTE",
    "ACTIONS_READ",
    "ALL_API_SCOPES",
    "APIAccessMode",
    "APIAuditPolicy",
    "APIAuthorizationDecision",
    "APIPrincipal",
    "APIPrincipalKind",
    "APIRouteSecurityPolicy",
    "APISensitivity",
    "CONFIG_READ",
    "CONFIG_WRITE",
    "CONTROL_READ",
    "CONTROL_WRITE",
    "DEBUG_READ",
    "MEDIA_READ",
    "MEDIA_WRITE",
    "MODELS_READ",
    "MODELS_MANAGE",
    "MODELS_SELECT",
    "RECORDINGS_READ",
    "RECORDINGS_WRITE",
    "ROLE_SCOPES",
    "SAFETY_READ",
    "SAFETY_WRITE",
    "SITL_INJECT",
    "STATUS_READ",
    "SYSTEM_ADMIN",
    "SYSTEM_READ",
    "TELEMETRY_READ",
    "authorize_api_request",
]
