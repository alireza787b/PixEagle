"""Runtime authentication and route authorization helpers for PixEagle APIs."""

from __future__ import annotations

from collections import deque
from http.cookies import SimpleCookie
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import threading
import time
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import parse_qs

from classes.api_exposure_policy import APIExposurePolicy, is_loopback_host
from classes.api_security_policy import resolve_route_security_policy
from classes.api_security_types import (
    APIAccessMode,
    APIAuditPolicy,
    APIAuthorizationDecision,
    APIPrincipal,
    APIPrincipalKind,
    APISensitivity,
    ROLE_SCOPES,
    authorize_api_request,
)
from classes.browser_user_store import (
    BrowserUserConflictError,
    BrowserUserInvariantError,
    BrowserUserMutationResult,
    BrowserUserNotFoundError,
    BrowserUserPersistenceError,
    BrowserUserPublicRecord,
    BrowserUserRecord,
    BrowserUserSnapshot,
    BrowserUserStore,
    BrowserUserStoreError,
    BrowserUserValidationError,
    DEFAULT_PBKDF2_ITERATIONS,
    MAX_AUTH_RECORD_FILE_BYTES,
    MAX_PASSWORD_SALT_BYTES,
    MAX_PBKDF2_ITERATIONS,
    MIN_PASSWORD_SALT_BYTES,
    MIN_PBKDF2_ITERATIONS,
    PASSWORD_DIGEST_BYTES,
    PBKDF2_SHA256_SCHEME,
    hash_password_pbkdf2_sha256,
    load_user_records,
    make_user_record,
    verify_password_pbkdf2_sha256,
)


API_AUTH_MODE_LOCAL_COMPAT = "local_compat"
API_AUTH_MODE_MACHINE_BEARER = "machine_bearer"
API_AUTH_MODE_BROWSER_SESSION = "browser_session"
SUPPORTED_API_AUTH_MODES = frozenset(
    {
        API_AUTH_MODE_BROWSER_SESSION,
        API_AUTH_MODE_LOCAL_COMPAT,
        API_AUTH_MODE_MACHINE_BEARER,
    }
)
TOKEN_QUERY_KEYS = frozenset({"access_token", "api_key", "token"})
DEFAULT_SESSION_COOKIE_NAME = "pixeagle_session"
DEFAULT_CSRF_HEADER_NAME = "x-pixeagle-csrf"
DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60
MIN_SESSION_TTL_SECONDS = 60
MAX_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_LOGIN_FAILURE_LIMIT = 5
DEFAULT_LOGIN_FAILURE_WINDOW_SECONDS = 60
DEFAULT_LOGIN_FAILURE_MAX_KEYS = 4096
DEFAULT_LOGIN_FAILURE_MAX_KEYS_PER_CLIENT = 128
DEFAULT_PASSWORD_HASH_CONCURRENCY = 1
ALLOW_UNAUTHENTICATED_MEDIA_STREAMING_KEY = "ALLOW_UNAUTHENTICATED_MEDIA_STREAMING"
UNAUTHENTICATED_MEDIA_STREAM_ENDPOINTS = frozenset(
    {
        ("GET", "/video_feed"),
        ("WEBSOCKET", "/ws/video_feed"),
    }
)
TOKEN_NAME_CHARS = frozenset(
    "!#$%&'*+-.^_`|~"
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
)
FORWARDED_CLIENT_HEADER_NAMES = frozenset(
    {
        "forwarded",
        "x-forwarded-for",
        "x-real-ip",
        "x-client-ip",
        "cf-connecting-ip",
        "true-client-ip",
    }
)
_DUMMY_PASSWORD_HASH: Optional[str] = None
_DUMMY_PASSWORD_HASH_LOCK = threading.RLock()


APIAuthConfigurationError = BrowserUserStoreError
APIUserRecord = BrowserUserRecord


@dataclass(frozen=True)
class BearerTokenRecord:
    """One hashed, revocable machine-token record."""

    token_id: str
    subject: str
    token_sha256: str
    scopes: frozenset[str]
    enabled: bool = True
    expires_at: Optional[datetime] = None

    def is_active(self, *, now: Optional[datetime] = None) -> bool:
        if not self.enabled:
            return False
        if self.expires_at is None:
            return True
        current = now or datetime.now(timezone.utc)
        return current < self.expires_at


@dataclass(frozen=True)
class APISessionRecord:
    """One in-memory browser/operator session."""

    session_id: str
    username: str
    role: str
    csrf_token: str
    created_at: float
    expires_at: float

    def is_active(self, *, now: Optional[float] = None) -> bool:
        return (now if now is not None else time.time()) < self.expires_at


class APISessionStore:
    """Small in-memory session store for the current FastAPI process."""

    def __init__(self) -> None:
        self._records: dict[str, APISessionRecord] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        *,
        username: str,
        role: str,
        ttl_seconds: int,
    ) -> APISessionRecord:
        now = time.time()
        record = APISessionRecord(
            session_id=secrets.token_urlsafe(32),
            username=username,
            role=role,
            csrf_token=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + max(1, int(ttl_seconds)),
        )
        with self._lock:
            self._records[record.session_id] = record
        return record

    def get(self, session_id: str) -> Optional[APISessionRecord]:
        normalized = str(session_id or "").strip()
        if not normalized:
            return None
        with self._lock:
            record = self._records.get(normalized)
            if record is not None and not record.is_active():
                self._records.pop(normalized, None)
                return None
            return record

    def revoke(self, session_id: str) -> bool:
        normalized = str(session_id or "").strip()
        if not normalized:
            return False
        with self._lock:
            return self._records.pop(normalized, None) is not None

    def revoke_username(self, username: str) -> int:
        """Revoke every session owned by one normalized browser username."""
        normalized = str(username or "").strip().lower()
        if not normalized:
            return 0
        with self._lock:
            session_ids = [
                session_id
                for session_id, record in self._records.items()
                if record.username.lower() == normalized
            ]
            for session_id in session_ids:
                self._records.pop(session_id, None)
            return len(session_ids)

    def revoke_all(self) -> int:
        """Revoke every active browser session."""
        with self._lock:
            revoked = len(self._records)
            self._records.clear()
            return revoked


class APILoginFailureLimiter:
    """Process-local failure throttle for the public browser login route."""

    def __init__(
        self,
        *,
        max_failures: int = DEFAULT_LOGIN_FAILURE_LIMIT,
        window_seconds: int = DEFAULT_LOGIN_FAILURE_WINDOW_SECONDS,
        max_keys: int = DEFAULT_LOGIN_FAILURE_MAX_KEYS,
        max_keys_per_client: int = DEFAULT_LOGIN_FAILURE_MAX_KEYS_PER_CLIENT,
    ) -> None:
        self.max_failures = max(1, int(max_failures))
        self.window_seconds = max(1, int(window_seconds))
        self.max_keys = max(1, int(max_keys))
        self.max_keys_per_client = max(1, int(max_keys_per_client))
        self._failures: dict[str, deque[float]] = {}
        self._client_failures: dict[str, deque[float]] = {}
        self._lock = threading.RLock()

    def is_allowed(self, key: str) -> tuple[bool, Optional[int]]:
        normalized = str(key or "").strip().lower() or "unknown"
        now = time.time()
        with self._lock:
            self._prune_all(now)
            client_failures = self._client_failures.get(
                _login_failure_client(normalized)
            )
            if client_failures and len(client_failures) >= self.max_failures:
                retry_after = int(
                    max(1.0, client_failures[0] + self.window_seconds - now)
                )
                return False, retry_after
            if normalized not in self._failures and not self._can_track_new_key(
                normalized,
            ):
                return False, self.window_seconds
            failures = self._failures.setdefault(normalized, deque())
            self._prune(failures, now)
            if len(failures) < self.max_failures:
                return True, None
            retry_after = int(max(1.0, failures[0] + self.window_seconds - now))
            return False, retry_after

    def record_failure(self, key: str) -> None:
        normalized = str(key or "").strip().lower() or "unknown"
        now = time.time()
        with self._lock:
            self._prune_all(now)
            if normalized not in self._failures and not self._can_track_new_key(
                normalized,
            ):
                return
            failures = self._failures.setdefault(normalized, deque())
            self._prune(failures, now)
            failures.append(now)
            client_failures = self._client_failures.setdefault(
                _login_failure_client(normalized),
                deque(),
            )
            self._prune(client_failures, now)
            client_failures.append(now)

    def clear(self, key: str) -> None:
        normalized = str(key or "").strip().lower() or "unknown"
        with self._lock:
            client = _login_failure_client(normalized)
            for existing_key in tuple(self._failures):
                if _login_failure_client(existing_key) == client:
                    self._failures.pop(existing_key, None)
            self._client_failures.pop(client, None)

    def _prune(self, failures: deque[float], now: float) -> None:
        while failures and failures[0] <= now - self.window_seconds:
            failures.popleft()

    def _prune_all(self, now: float) -> None:
        expired = []
        for key, failures in self._failures.items():
            self._prune(failures, now)
            if not failures:
                expired.append(key)
        for key in expired:
            self._failures.pop(key, None)
        expired_clients = []
        for client, failures in self._client_failures.items():
            self._prune(failures, now)
            if not failures:
                expired_clients.append(client)
        for client in expired_clients:
            self._client_failures.pop(client, None)

    def _can_track_new_key(self, key: str) -> bool:
        if len(self._failures) >= self.max_keys:
            return False
        client = _login_failure_client(key)
        client_keys = sum(
            1
            for existing_key in self._failures
            if _login_failure_client(existing_key) == client
        )
        return client_keys < self.max_keys_per_client


@dataclass(frozen=True)
class APIAuthRuntime:
    """Authentication runtime used by HTTP and WebSocket route guards."""

    mode: str
    bearer_tokens_by_hash: Mapping[str, BearerTokenRecord] = field(
        default_factory=lambda: MappingProxyType({})
    )
    token_file: Optional[Path] = None
    users_by_username: Mapping[str, APIUserRecord] = field(
        default_factory=lambda: MappingProxyType({})
    )
    user_file: Optional[Path] = None
    user_store: Optional[BrowserUserStore] = field(default=None, repr=False, compare=False)
    session_store: APISessionStore = field(default_factory=APISessionStore)
    login_failure_limiter: APILoginFailureLimiter = field(
        default_factory=APILoginFailureLimiter
    )
    _password_hash_capacity: threading.BoundedSemaphore = field(
        default_factory=lambda: threading.BoundedSemaphore(
            DEFAULT_PASSWORD_HASH_CONCURRENCY
        ),
        repr=False,
        compare=False,
    )
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    session_cookie_name: str = DEFAULT_SESSION_COOKIE_NAME
    session_cookie_secure: bool = False
    csrf_header_name: str = DEFAULT_CSRF_HEADER_NAME
    allow_unauthenticated_media_streaming: bool = False
    _user_mutation_lock: threading.RLock = field(
        default_factory=threading.RLock,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        normalized_mode = str(self.mode or "").strip().lower()
        if normalized_mode not in SUPPORTED_API_AUTH_MODES:
            supported = ", ".join(sorted(SUPPORTED_API_AUTH_MODES))
            raise APIAuthConfigurationError(
                f"Unsupported API auth mode {self.mode!r}; supported modes: {supported}"
            )
        object.__setattr__(self, "mode", normalized_mode)
        object.__setattr__(
            self,
            "bearer_tokens_by_hash",
            MappingProxyType(dict(self.bearer_tokens_by_hash or {})),
        )
        store = self.user_store
        if store is None and self.user_file is not None:
            store = BrowserUserStore(self.user_file)
        object.__setattr__(self, "user_store", store)
        object.__setattr__(
            self,
            "_user_mutation_lock",
            store.mutation_lock if store is not None else threading.RLock(),
        )
        normalized_users = BrowserUserSnapshot.from_records(
            (self.users_by_username or {}).values()
        ).records_by_username
        object.__setattr__(
            self,
            "users_by_username",
            normalized_users,
        )
        object.__setattr__(
            self,
            "session_ttl_seconds",
            _normalize_bounded_int(
                self.session_ttl_seconds,
                "API_SESSION_TTL_SECONDS",
                minimum=MIN_SESSION_TTL_SECONDS,
                maximum=MAX_SESSION_TTL_SECONDS,
            ),
        )
        object.__setattr__(
            self,
            "session_cookie_name",
            _normalize_cookie_or_header_name(
                self.session_cookie_name,
                "API_SESSION_COOKIE_NAME",
            ),
        )
        object.__setattr__(
            self,
            "csrf_header_name",
            _normalize_cookie_or_header_name(
                self.csrf_header_name,
                "API_CSRF_HEADER_NAME",
            ).lower(),
        )
        object.__setattr__(
            self,
            "allow_unauthenticated_media_streaming",
            _coerce_bool(
                self.allow_unauthenticated_media_streaming,
                ALLOW_UNAUTHENTICATED_MEDIA_STREAMING_KEY,
            ),
        )
        if normalized_mode == API_AUTH_MODE_MACHINE_BEARER and not any(
            record.enabled for record in self.bearer_tokens_by_hash.values()
        ):
            raise APIAuthConfigurationError(
                "API_AUTH_MODE=machine_bearer requires at least one enabled "
                "bearer token record"
            )
        if normalized_mode == API_AUTH_MODE_BROWSER_SESSION and not any(
            record.enabled for record in self.users_by_username.values()
        ):
            raise APIAuthConfigurationError(
                "API_AUTH_MODE=browser_session requires at least one enabled "
                "user record"
            )

    @property
    def local_compat_enabled(self) -> bool:
        return self.mode == API_AUTH_MODE_LOCAL_COMPAT

    @property
    def browser_sessions_enabled(self) -> bool:
        return self.mode == API_AUTH_MODE_BROWSER_SESSION

    def principal_from_authorization_header(
        self,
        authorization_header: Optional[str],
    ) -> tuple[APIPrincipal, Optional[str]]:
        """Return a principal plus an authentication failure reason when present."""
        scheme, credential = _parse_authorization_header(authorization_header)
        if scheme is None and credential is None:
            return APIPrincipal.anonymous(), None
        if scheme != "bearer" or not credential:
            return APIPrincipal.anonymous(), "unsupported_authorization_scheme"

        token_hash = hash_bearer_token(credential)
        record = self.bearer_tokens_by_hash.get(token_hash)
        if record is None:
            return APIPrincipal.anonymous(), "invalid_bearer_token"
        if not record.is_active():
            return APIPrincipal.anonymous(), "inactive_bearer_token"

        return (
            APIPrincipal.bearer(
                token_id=record.token_id,
                subject=record.subject,
                scopes=record.scopes,
            ),
            None,
        )

    def principal_from_session_cookie(
        self,
        cookie_header: Optional[str],
    ) -> tuple[APIPrincipal, Optional[str], Optional[APISessionRecord]]:
        """Return a session principal plus an auth failure reason when present."""
        if not self.browser_sessions_enabled:
            return APIPrincipal.anonymous(), None, None
        session_id = _cookie_value(cookie_header, self.session_cookie_name)
        if not session_id:
            return APIPrincipal.anonymous(), None, None

        session = self.session_store.get(session_id)
        if session is None:
            return APIPrincipal.anonymous(), "invalid_session", None
        try:
            principal = APIPrincipal.session(
                username=session.username,
                role=session.role,
                session_id=session.session_id,
            )
        except ValueError:
            self.session_store.revoke(session_id)
            return APIPrincipal.anonymous(), "invalid_session", None
        return principal, None, session

    def authenticate_user(
        self,
        *,
        username: str,
        password: str,
    ) -> Optional[APIUserRecord]:
        """Return the enabled user when the supplied password verifies."""
        with self._user_mutation_lock:
            return self._authenticate_user_unlocked(
                username=username,
                password=password,
            )

    def _authenticate_user_unlocked(
        self,
        *,
        username: str,
        password: str,
    ) -> Optional[APIUserRecord]:
        if not self.browser_sessions_enabled:
            return None
        normalized_username = str(username or "").strip().lower()
        user = self.users_by_username.get(normalized_username)
        if user is None or not user.enabled:
            verify_password_pbkdf2_sha256(
                password=password,
                encoded=_dummy_password_hash(),
            )
            return None
        if not verify_password_pbkdf2_sha256(
            password=password,
            encoded=user.password_pbkdf2_sha256,
        ):
            return None
        return user

    def create_session_for_user(self, user: APIUserRecord) -> APISessionRecord:
        """Create one in-memory session for a verified browser/operator user."""
        with self._user_mutation_lock:
            current = self.users_by_username.get(str(user.username).strip().lower())
            if current is None or not current.enabled or current != user:
                raise APIAuthConfigurationError(
                    "Cannot create a session from a stale or disabled browser-user record"
                )
            return self._create_session_unlocked(current)

    def authenticate_and_create_session(
        self,
        *,
        username: str,
        password: str,
    ) -> Optional[tuple[APIUserRecord, APISessionRecord]]:
        """Verify current credentials and create the session under one user lock."""
        with self._user_mutation_lock:
            user = self._authenticate_user_unlocked(
                username=username,
                password=password,
            )
            if user is None:
                return None
            return user, self._create_session_unlocked(user)

    def _create_session_unlocked(self, user: APIUserRecord) -> APISessionRecord:
        return self.session_store.create_session(
            username=user.username,
            role=user.role,
            ttl_seconds=self.session_ttl_seconds,
        )

    def revoke_session_id(self, session_id: Optional[str]) -> bool:
        """Revoke one in-memory session by id."""
        return self.session_store.revoke(session_id or "")

    def revoke_username(self, username: str) -> int:
        """Revoke every active session for one browser username."""
        with self._user_mutation_lock:
            return self.session_store.revoke_username(username)

    def refresh_user_snapshot(
        self,
        records: Optional[Iterable[APIUserRecord]] = None,
    ) -> Mapping[str, APIUserRecord]:
        """Atomically publish a validated immutable user snapshot in-place."""
        with self._user_mutation_lock:
            if records is None:
                store = self._require_user_store_unlocked()
                snapshot = store.load_snapshot()
            else:
                snapshot = BrowserUserSnapshot.from_records(records)
            if self.browser_sessions_enabled and not any(
                record.enabled for record in snapshot.records
            ):
                raise APIAuthConfigurationError(
                    "API_AUTH_MODE=browser_session requires at least one enabled user record"
                )
            object.__setattr__(self, "users_by_username", snapshot.records_by_username)
            return self.users_by_username

    def browser_user_public_snapshot(self) -> tuple[BrowserUserPublicRecord, ...]:
        """Return credential-free metadata from the current immutable snapshot."""
        with self._user_mutation_lock:
            return tuple(
                record.public() for record in self.users_by_username.values()
            )

    def create_browser_user(
        self,
        *,
        username: str,
        password: str,
        role: str,
        enabled: bool,
    ) -> BrowserUserMutationResult:
        with self._user_mutation_lock:
            store = self._require_user_store_unlocked()
            try:
                result = store.create_user(
                    username=username,
                    plaintext_password=password,
                    role=role,
                    enabled=enabled,
                    create_if_missing=False,
                    require_enabled_admin=True,
                )
            except BrowserUserPersistenceError:
                self._reconcile_after_persistence_error_unlocked(store)
                raise
            self._publish_mutation_snapshot_unlocked(result)
            return result

    def update_browser_user(
        self,
        username: str,
        *,
        role: Optional[str] = None,
        enabled: Optional[bool] = None,
        password: Optional[str] = None,
    ) -> tuple[BrowserUserMutationResult, int]:
        with self._user_mutation_lock:
            store = self._require_user_store_unlocked()
            try:
                result = store.update_user(
                    username,
                    role=role,
                    enabled=enabled,
                    plaintext_password=password,
                    require_enabled_admin=True,
                )
            except BrowserUserPersistenceError:
                self._reconcile_after_persistence_error_unlocked(store)
                raise
            self._publish_mutation_snapshot_unlocked(result)
            revoked = self.session_store.revoke_username(username)
            return result, revoked

    def delete_browser_user(
        self,
        username: str,
    ) -> tuple[BrowserUserMutationResult, int]:
        with self._user_mutation_lock:
            store = self._require_user_store_unlocked()
            try:
                result = store.delete_user(
                    username,
                    require_enabled_admin=True,
                )
            except BrowserUserPersistenceError:
                self._reconcile_after_persistence_error_unlocked(store)
                raise
            self._publish_mutation_snapshot_unlocked(result)
            revoked = self.session_store.revoke_username(username)
            return result, revoked

    def change_browser_user_password(
        self,
        *,
        username: str,
        current_password: str,
        new_password: str,
    ) -> Optional[tuple[BrowserUserMutationResult, APISessionRecord, int]]:
        """Persist a self password change and replace every session atomically."""
        with self._user_mutation_lock:
            user = self._authenticate_user_unlocked(
                username=username,
                password=current_password,
            )
            if user is None:
                return None
            store = self._require_user_store_unlocked()
            try:
                result = store.update_user(
                    user.username,
                    plaintext_password=new_password,
                )
            except BrowserUserPersistenceError:
                self._reconcile_after_persistence_error_unlocked(store)
                raise
            self._publish_mutation_snapshot_unlocked(result)
            revoked = self.session_store.revoke_username(user.username)
            current = self.users_by_username[user.username]
            replacement = self._create_session_unlocked(current)
            return result, replacement, revoked

    def _publish_mutation_snapshot_unlocked(
        self,
        result: BrowserUserMutationResult,
    ) -> None:
        object.__setattr__(
            self,
            "users_by_username",
            result.snapshot.records_by_username,
        )

    def _reconcile_after_persistence_error_unlocked(
        self,
        store: BrowserUserStore,
    ) -> None:
        """Fail closed if a write may have reached disk before reporting error."""
        self.session_store.revoke_all()
        try:
            snapshot = store.load_snapshot()
        except BrowserUserStoreError:
            object.__setattr__(
                self,
                "users_by_username",
                MappingProxyType({}),
            )
            return
        object.__setattr__(self, "users_by_username", snapshot.records_by_username)

    def _require_user_store_unlocked(self) -> BrowserUserStore:
        if not self.browser_sessions_enabled or self.user_store is None:
            raise BrowserUserPersistenceError(
                "Browser-session account management requires API_AUTH_MODE="
                "browser_session with an external API_SESSION_USER_FILE"
            )
        return self.user_store

    def session_record_for_principal(
        self,
        principal: APIPrincipal,
    ) -> Optional[APISessionRecord]:
        if principal.kind != APIPrincipalKind.SESSION:
            return None
        return self.session_store.get(principal.credential_id or "")

    def principal_session_is_active(self, principal: APIPrincipal) -> bool:
        """Return whether a session principal still maps to an active session."""
        if principal.kind != APIPrincipalKind.SESSION:
            return True
        return self.session_record_for_principal(principal) is not None

    def csrf_token_is_valid(
        self,
        session: Optional[APISessionRecord],
        headers: Mapping[str, str],
    ) -> bool:
        if session is None:
            return False
        provided = _header_get(headers, self.csrf_header_name)
        if not provided:
            return False
        return hmac.compare_digest(str(provided), session.csrf_token)

    def login_attempt_allowed(self, key: str) -> tuple[bool, Optional[int]]:
        """Return whether a browser login attempt may run for the key."""
        return self.login_failure_limiter.is_allowed(key)

    def record_login_failure(self, key: str) -> None:
        """Record one failed browser login attempt."""
        self.login_failure_limiter.record_failure(key)

    def clear_login_failures(self, key: str) -> None:
        """Clear failure history after successful browser login."""
        self.login_failure_limiter.clear(key)

    def try_acquire_password_hash_slot(self) -> bool:
        """Reserve bounded password hashing or verification capacity."""
        return self._password_hash_capacity.acquire(blocking=False)

    def release_password_hash_slot(self) -> None:
        """Release one password hashing or verification reservation."""
        self._password_hash_capacity.release()


@dataclass(frozen=True)
class APITransportAuthorizationResult:
    """HTTP/WebSocket authorization result with no credential material."""

    allowed: bool
    status_code: int
    reason: str
    principal: APIPrincipal
    decision: APIAuthorizationDecision
    audit_policy: APIAuditPolicy
    sensitivity: APISensitivity
    missing_scopes: tuple[str, ...] = ()

    @property
    def is_authentication_failure(self) -> bool:
        return self.status_code == 401


def hash_bearer_token(token: str) -> str:
    """Hash a high-entropy bearer token for storage and lookup."""
    raw = str(token or "").strip()
    if not raw:
        raise APIAuthConfigurationError("Bearer token must not be empty")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_auth_record_json(path: Path, *, label: str) -> Any:
    record_path = Path(path).expanduser()
    open_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    no_follow_flag = getattr(os, "O_NOFOLLOW", 0)
    if no_follow_flag:
        open_flags |= no_follow_flag
    elif record_path.is_symlink():
        raise APIAuthConfigurationError(f"{label} must not be a symbolic link: {record_path}")

    descriptor: Optional[int] = None
    try:
        descriptor = os.open(record_path, open_flags)
        file_status = os.fstat(descriptor)
        if not stat.S_ISREG(file_status.st_mode):
            raise APIAuthConfigurationError(f"{label} must be a regular file: {record_path}")
        if file_status.st_nlink != 1:
            raise APIAuthConfigurationError(f"{label} must not have multiple hard links: {record_path}")
        if os.name == "posix":
            if file_status.st_uid != os.geteuid():
                raise APIAuthConfigurationError(
                    f"{label} must be owned by the PixEagle process user: {record_path}"
                )
            permissions = stat.S_IMODE(file_status.st_mode)
            if not permissions & stat.S_IRUSR or permissions & 0o077:
                raise APIAuthConfigurationError(
                    f"{label} must be owner-readable and inaccessible to group/other users: {record_path}"
                )
        if file_status.st_size > MAX_AUTH_RECORD_FILE_BYTES:
            raise APIAuthConfigurationError(
                f"{label} exceeds the {MAX_AUTH_RECORD_FILE_BYTES} byte limit: {record_path}"
            )

        with os.fdopen(descriptor, "rb") as record_file:
            descriptor = None
            raw_payload = record_file.read(MAX_AUTH_RECORD_FILE_BYTES + 1)
        if len(raw_payload) > MAX_AUTH_RECORD_FILE_BYTES:
            raise APIAuthConfigurationError(
                f"{label} exceeds the {MAX_AUTH_RECORD_FILE_BYTES} byte limit: {record_path}"
            )
        return json.loads(raw_payload.decode("utf-8"))
    except FileNotFoundError as exc:
        raise APIAuthConfigurationError(f"{label} does not exist: {record_path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise APIAuthConfigurationError(f"{label} could not be read safely: {record_path}") from exc
    except json.JSONDecodeError as exc:
        raise APIAuthConfigurationError(f"Invalid {label} JSON: {record_path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_bearer_token_records(path: Path) -> tuple[BearerTokenRecord, ...]:
    """Load machine bearer token records from JSON outside checked-in config."""
    token_path = Path(path).expanduser()
    payload = _load_auth_record_json(token_path, label="API bearer token file")

    raw_records = payload.get("tokens") if isinstance(payload, dict) else payload
    if not isinstance(raw_records, list):
        raise APIAuthConfigurationError("API bearer token file must contain a tokens list")

    records = tuple(
        _parse_bearer_token_record(item, index)
        for index, item in enumerate(raw_records)
    )
    hashes = [record.token_sha256 for record in records]
    if len(hashes) != len(set(hashes)):
        raise APIAuthConfigurationError("Duplicate API bearer token hashes are not allowed")
    return records


def resolve_api_auth_runtime_from_parameters(parameters) -> APIAuthRuntime:
    """Build the API auth runtime from flattened Parameters without secrets."""
    raw_config = getattr(parameters, "_raw_config", {})
    raw_streaming = raw_config.get("Streaming", {}) if isinstance(raw_config, dict) else {}
    if not isinstance(raw_streaming, dict):
        raw_streaming = {}

    mode = raw_streaming.get(
        "API_AUTH_MODE",
        getattr(parameters, "API_AUTH_MODE", API_AUTH_MODE_LOCAL_COMPAT),
    )
    token_file_value = raw_streaming.get(
        "API_BEARER_TOKEN_FILE",
        getattr(parameters, "API_BEARER_TOKEN_FILE", ""),
    )
    user_file_value = raw_streaming.get(
        "API_SESSION_USER_FILE",
        getattr(parameters, "API_SESSION_USER_FILE", ""),
    )
    token_path = _normalize_optional_file_path(token_file_value)
    user_path = _normalize_optional_file_path(user_file_value)
    records = load_bearer_token_records(token_path) if token_path is not None else ()
    user_store = BrowserUserStore(user_path) if user_path is not None else None
    users = user_store.load_snapshot().records if user_store is not None else ()
    return APIAuthRuntime(
        mode=mode,
        bearer_tokens_by_hash={record.token_sha256: record for record in records},
        token_file=token_path,
        users_by_username={record.username: record for record in users},
        user_file=user_path,
        user_store=user_store,
        session_ttl_seconds=raw_streaming.get(
            "API_SESSION_TTL_SECONDS",
            getattr(parameters, "API_SESSION_TTL_SECONDS", DEFAULT_SESSION_TTL_SECONDS),
        ),
        session_cookie_name=raw_streaming.get(
            "API_SESSION_COOKIE_NAME",
            getattr(parameters, "API_SESSION_COOKIE_NAME", DEFAULT_SESSION_COOKIE_NAME),
        ),
        session_cookie_secure=_coerce_bool(
            raw_streaming.get(
                "API_SESSION_COOKIE_SECURE",
                getattr(parameters, "API_SESSION_COOKIE_SECURE", False),
            ),
            "API_SESSION_COOKIE_SECURE",
        ),
        csrf_header_name=raw_streaming.get(
            "API_CSRF_HEADER_NAME",
            getattr(parameters, "API_CSRF_HEADER_NAME", DEFAULT_CSRF_HEADER_NAME),
        ),
        allow_unauthenticated_media_streaming=_coerce_bool(
            raw_streaming.get(
                ALLOW_UNAUTHENTICATED_MEDIA_STREAMING_KEY,
                getattr(parameters, ALLOW_UNAUTHENTICATED_MEDIA_STREAMING_KEY, False),
            ),
            ALLOW_UNAUTHENTICATED_MEDIA_STREAMING_KEY,
        ),
    )


def authorize_http_request(
    *,
    runtime: APIAuthRuntime,
    method: str,
    path: str,
    headers: Mapping[str, str],
    client_host: Optional[str],
    host_header: Optional[str],
    exposure_policy: APIExposurePolicy,
    query_params: Optional[Mapping[str, Any]] = None,
) -> APITransportAuthorizationResult:
    """Authorize one HTTP route after exposure Host/Origin checks pass."""
    return _authorize_transport(
        runtime=runtime,
        method=method,
        path=path,
        headers=headers,
        client_host=client_host,
        host_header=host_header,
        exposure_policy=exposure_policy,
        query_params=query_params,
    )


def authorize_websocket_request(
    *,
    runtime: APIAuthRuntime,
    path: str,
    headers: Mapping[str, str],
    client_host: Optional[str],
    host_header: Optional[str],
    exposure_policy: APIExposurePolicy,
    query_string: str = "",
) -> APITransportAuthorizationResult:
    """Authorize one WebSocket route before accept()."""
    return _authorize_transport(
        runtime=runtime,
        method="WEBSOCKET",
        path=path,
        headers=headers,
        client_host=client_host,
        host_header=host_header,
        exposure_policy=exposure_policy,
        query_params=parse_qs(query_string, keep_blank_values=True),
    )


def is_loopback_transport_client(
    *,
    client_host: Optional[str],
    host_header: Optional[str],
    exposure_policy: APIExposurePolicy,
    headers: Optional[Mapping[str, str]] = None,
) -> bool:
    """Identify local-compat clients from the socket peer, not HTTP Host."""
    _ = host_header, exposure_policy
    if has_proxy_forwarded_client_headers(headers):
        return False
    return is_loopback_host(client_host or "")


def has_proxy_forwarded_client_headers(
    headers: Optional[Mapping[str, str]],
) -> bool:
    """Return true when a proxy/client-forwarding identity header is present."""
    if not headers:
        return False
    return any(
        bool(str(_header_get(headers, header_name) or "").strip())
        for header_name in FORWARDED_CLIENT_HEADER_NAMES
    )


def make_token_record(
    *,
    token_id: str,
    plaintext_token: str,
    scopes: Iterable[str],
    subject: str = "machine-client",
    enabled: bool = True,
) -> dict[str, Any]:
    """Build a token-file record for tests/tools without logging secrets."""
    return {
        "token_id": token_id,
        "subject": subject,
        "token_sha256": hash_bearer_token(plaintext_token),
        "scopes": list(scopes),
        "enabled": enabled,
    }


def _authorize_transport(
    *,
    runtime: APIAuthRuntime,
    method: str,
    path: str,
    headers: Mapping[str, str],
    client_host: Optional[str],
    host_header: Optional[str],
    exposure_policy: APIExposurePolicy,
    query_params: Optional[Mapping[str, Any]],
) -> APITransportAuthorizationResult:
    anonymous = APIPrincipal.anonymous()
    normalized_method = str(method or "").strip().upper()
    policy = resolve_route_security_policy(method, path)
    if _contains_query_token(query_params):
        return _result(
            False,
            401,
            "query_token_not_supported",
            anonymous,
            audit_policy=policy.audit,
            sensitivity=policy.sensitivity,
        )

    is_loopback_client = is_loopback_transport_client(
        client_host=client_host,
        host_header=host_header,
        exposure_policy=exposure_policy,
        headers=headers,
    )
    forwarded_loopback_peer = (
        is_loopback_host(client_host or "")
        and has_proxy_forwarded_client_headers(headers)
    )
    principal, auth_error = runtime.principal_from_authorization_header(
        _header_get(headers, "authorization")
    )
    if auth_error is not None:
        return _result(
            False,
            401,
            auth_error,
            anonymous,
            audit_policy=policy.audit,
            sensitivity=policy.sensitivity,
        )

    anonymous_media_stream_allowed = (
        runtime.allow_unauthenticated_media_streaming
        and (normalized_method, path) in UNAUTHENTICATED_MEDIA_STREAM_ENDPOINTS
    )

    session_record: Optional[APISessionRecord] = None
    if principal.kind == APIPrincipalKind.ANONYMOUS:
        principal, session_error, session_record = runtime.principal_from_session_cookie(
            _header_get(headers, "cookie")
        )
        if session_error is not None:
            if policy.access == APIAccessMode.PUBLIC or anonymous_media_stream_allowed:
                principal = anonymous
                session_record = None
            else:
                return _result(
                    False,
                    401,
                    session_error,
                    anonymous,
                    audit_policy=policy.audit,
                    sensitivity=policy.sensitivity,
                )

    if principal.kind == APIPrincipalKind.ANONYMOUS and anonymous_media_stream_allowed:
        return _result(
            True,
            200,
            "unauthenticated_media_streaming_allowed",
            anonymous,
            audit_policy=policy.audit,
            sensitivity=policy.sensitivity,
        )

    if principal.kind == APIPrincipalKind.ANONYMOUS and policy.access != APIAccessMode.PUBLIC:
        if runtime.local_compat_enabled and is_loopback_client:
            principal = APIPrincipal.local_compat()
        elif runtime.local_compat_enabled and forwarded_loopback_peer:
            return _result(
                False,
                401,
                "proxy_forwarded_local_compat_not_allowed",
                anonymous,
                audit_policy=policy.audit,
                sensitivity=policy.sensitivity,
            )

    csrf_valid = False
    if principal.kind == APIPrincipalKind.SESSION:
        session_record = session_record or runtime.session_record_for_principal(principal)
        csrf_valid = runtime.csrf_token_is_valid(session_record, headers)

    decision = authorize_api_request(
        policy=policy,
        principal=principal,
        is_loopback_client=is_loopback_client,
        csrf_valid=csrf_valid,
    )
    if decision.allowed:
        return APITransportAuthorizationResult(
            allowed=True,
            status_code=200,
            reason="allowed",
            principal=principal,
            decision=decision,
            audit_policy=policy.audit,
            sensitivity=policy.sensitivity,
        )

    status_code = 401 if decision.reason == "authentication_required" else 403
    return APITransportAuthorizationResult(
        allowed=False,
        status_code=status_code,
        reason=decision.reason,
        principal=principal,
        decision=decision,
        audit_policy=policy.audit,
        sensitivity=policy.sensitivity,
        missing_scopes=decision.missing_scopes,
    )


def _parse_bearer_token_record(raw: Any, index: int) -> BearerTokenRecord:
    if not isinstance(raw, dict):
        raise APIAuthConfigurationError(f"Token record {index} must be an object")

    token_id = str(raw.get("token_id") or "").strip()
    subject = str(raw.get("subject") or token_id).strip()
    token_sha256 = str(raw.get("token_sha256") or "").strip().lower()
    scopes = raw.get("scopes")
    enabled = _parse_json_bool(raw.get("enabled", True), f"Token record {token_id!r} enabled")
    expires_at = _parse_optional_datetime(raw.get("expires_at"), index)

    if not token_id:
        raise APIAuthConfigurationError(f"Token record {index} missing token_id")
    if not subject:
        raise APIAuthConfigurationError(f"Token record {index} missing subject")
    if len(token_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in token_sha256
    ):
        raise APIAuthConfigurationError(
            f"Token record {token_id!r} has invalid token_sha256"
        )
    if not isinstance(scopes, list) or not scopes:
        raise APIAuthConfigurationError(f"Token record {token_id!r} must declare scopes")

    try:
        principal = APIPrincipal.bearer(
            token_id=token_id,
            subject=subject,
            scopes=scopes,
        )
    except ValueError as exc:
        raise APIAuthConfigurationError(str(exc)) from exc

    return BearerTokenRecord(
        token_id=token_id,
        subject=subject,
        token_sha256=token_sha256,
        scopes=principal.scopes,
        enabled=enabled,
        expires_at=expires_at,
    )


def _parse_authorization_header(header: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    raw = str(header or "").strip()
    if not raw:
        return None, None
    parts = raw.split(None, 1)
    if len(parts) != 2:
        return raw.lower(), None
    return parts[0].lower(), parts[1].strip()


def _parse_optional_datetime(value: Any, index: int) -> Optional[datetime]:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise APIAuthConfigurationError(
            f"Token record {index} expires_at must be a string"
        )
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise APIAuthConfigurationError(
            f"Token record {index} has invalid expires_at"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dummy_password_hash() -> str:
    global _DUMMY_PASSWORD_HASH
    with _DUMMY_PASSWORD_HASH_LOCK:
        if _DUMMY_PASSWORD_HASH is None:
            _DUMMY_PASSWORD_HASH = hash_password_pbkdf2_sha256(
                "pixeagle-dummy-password",
                salt=b"pixeagle-auth-dummy-salt",
                iterations=DEFAULT_PBKDF2_ITERATIONS,
            )
        return _DUMMY_PASSWORD_HASH


def _normalize_optional_file_path(value: Any) -> Optional[Path]:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def _normalize_optional_token_path(value: Any) -> Optional[Path]:
    return _normalize_optional_file_path(value)


def _cookie_value(cookie_header: Optional[str], cookie_name: str) -> Optional[str]:
    raw = str(cookie_header or "")
    if not raw:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(raw)
    except Exception:
        return None
    morsel = cookie.get(cookie_name)
    if morsel is None:
        return None
    return str(morsel.value or "").strip() or None


def _normalize_positive_int(value: Any, name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise APIAuthConfigurationError(f"{name} must be a positive integer") from exc
    if normalized < 1:
        raise APIAuthConfigurationError(f"{name} must be a positive integer")
    return normalized


def _normalize_bounded_int(
    value: Any,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    normalized = _normalize_positive_int(value, name)
    if normalized < minimum or normalized > maximum:
        raise APIAuthConfigurationError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return normalized


def _coerce_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise APIAuthConfigurationError(f"{name} must be a boolean")


def _parse_json_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise APIAuthConfigurationError(f"{name} must be a JSON boolean")


def _normalize_cookie_or_header_name(value: Any, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise APIAuthConfigurationError(f"{name} must not be empty")
    if any(char not in TOKEN_NAME_CHARS for char in normalized):
        raise APIAuthConfigurationError(f"{name} contains unsupported characters")
    return normalized


def _login_failure_client(key: str) -> str:
    client, _separator, _rest = str(key or "").partition(":")
    return client or "unknown"


def _contains_query_token(query_params: Optional[Mapping[str, Any]]) -> bool:
    if not query_params:
        return False
    return any(str(key).lower() in TOKEN_QUERY_KEYS for key in query_params.keys())


def _header_get(headers: Mapping[str, str], name: str) -> Optional[str]:
    if not hasattr(headers, "get"):
        return None
    target = name.lower()
    if hasattr(headers, "items"):
        for key, value in headers.items():
            if str(key).lower() == target:
                return value
    return headers.get(name) or headers.get(name.title())


def _result(
    allowed: bool,
    status_code: int,
    reason: str,
    principal: APIPrincipal,
    *,
    audit_policy: APIAuditPolicy = APIAuditPolicy.SECURITY_CRITICAL,
    sensitivity: APISensitivity = APISensitivity.UNKNOWN,
) -> APITransportAuthorizationResult:
    return APITransportAuthorizationResult(
        allowed=allowed,
        status_code=status_code,
        reason=reason,
        principal=principal,
        decision=APIAuthorizationDecision(allowed, reason),
        audit_policy=audit_policy,
        sensitivity=sensitivity,
    )


__all__ = [
    "API_AUTH_MODE_BROWSER_SESSION",
    "API_AUTH_MODE_LOCAL_COMPAT",
    "API_AUTH_MODE_MACHINE_BEARER",
    "ALLOW_UNAUTHENTICATED_MEDIA_STREAMING_KEY",
    "APIAuthConfigurationError",
    "APIAuthRuntime",
    "APILoginFailureLimiter",
    "APISessionRecord",
    "APISessionStore",
    "APITransportAuthorizationResult",
    "APIUserRecord",
    "BearerTokenRecord",
    "DEFAULT_CSRF_HEADER_NAME",
    "DEFAULT_LOGIN_FAILURE_LIMIT",
    "DEFAULT_LOGIN_FAILURE_MAX_KEYS",
    "DEFAULT_LOGIN_FAILURE_MAX_KEYS_PER_CLIENT",
    "DEFAULT_LOGIN_FAILURE_WINDOW_SECONDS",
    "MAX_SESSION_TTL_SECONDS",
    "MAX_PBKDF2_ITERATIONS",
    "MAX_PASSWORD_SALT_BYTES",
    "MIN_SESSION_TTL_SECONDS",
    "MIN_PBKDF2_ITERATIONS",
    "MIN_PASSWORD_SALT_BYTES",
    "PASSWORD_DIGEST_BYTES",
    "DEFAULT_PBKDF2_ITERATIONS",
    "DEFAULT_SESSION_COOKIE_NAME",
    "DEFAULT_SESSION_TTL_SECONDS",
    "FORWARDED_CLIENT_HEADER_NAMES",
    "PBKDF2_SHA256_SCHEME",
    "SUPPORTED_API_AUTH_MODES",
    "UNAUTHENTICATED_MEDIA_STREAM_ENDPOINTS",
    "authorize_http_request",
    "authorize_websocket_request",
    "hash_bearer_token",
    "hash_password_pbkdf2_sha256",
    "has_proxy_forwarded_client_headers",
    "is_loopback_transport_client",
    "load_bearer_token_records",
    "load_user_records",
    "make_token_record",
    "make_user_record",
    "resolve_api_auth_runtime_from_parameters",
    "verify_password_pbkdf2_sha256",
]
