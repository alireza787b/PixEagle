"""Focused bearer-token persistence and hot-revocation contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import threading

import pytest

from classes.api_auth_runtime import API_AUTH_MODE_BROWSER_SESSION, APIAuthRuntime
from classes.api_security_types import APIPrincipalKind, MEDIA_READ, STATUS_READ
from classes.bearer_token_store import (
    BearerTokenPersistenceError,
    BearerTokenStore,
    BearerTokenValidationError,
    hash_bearer_token,
    load_bearer_token_records,
    make_token_record,
)
from classes.browser_user_store import make_browser_user_record


def _runtime(token_path, token_store):
    admin = make_browser_user_record(
        username="admin",
        plaintext_password="admin-password",
        role="admin",
    )
    return APIAuthRuntime(
        mode=API_AUTH_MODE_BROWSER_SESSION,
        bearer_tokens_by_hash={},
        token_file=token_path,
        token_store=token_store,
        users_by_username={admin.username: admin},
    )


def test_create_lists_and_idempotently_revokes_without_persisting_plaintext(tmp_path):
    path = tmp_path / "tokens.json"
    store = BearerTokenStore(path)
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    created = store.create_token(
        display_name="QGC video",
        scopes=[MEDIA_READ],
        expires_at=expires_at,
    )

    assert created.plaintext_token is not None
    assert created.plaintext_token.startswith("pxe_")
    assert created.record.display_name == "QGC video"
    assert created.record.state == "active"
    assert created.record.scopes == frozenset({MEDIA_READ})
    assert path.stat().st_mode & 0o777 == 0o600
    serialized = path.read_text(encoding="utf-8")
    assert created.plaintext_token not in serialized
    assert "token_sha256" in serialized

    snapshot = store.load_snapshot()
    assert snapshot.public_records == (created.record,)
    revoked = store.revoke_token(created.record.token_id)
    assert revoked.changed is True
    assert revoked.plaintext_token is None
    assert revoked.record.state == "revoked"
    assert revoked.record.revoked_at is not None

    repeated = store.revoke_token(created.record.token_id)
    assert repeated.changed is False
    assert repeated.record.state == "revoked"


def test_legacy_token_records_remain_compatible_and_metadata_is_hash_free(tmp_path):
    path = tmp_path / "tokens.json"
    payload = {
        "tokens": [
            make_token_record(
                token_id="legacy-qgc",
                plaintext_token="legacy-secret",
                subject="qgc",
                scopes=[MEDIA_READ],
            )
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)

    records = load_bearer_token_records(path)

    assert len(records) == 1
    assert records[0].display_name is None
    public = records[0].public()
    assert public.display_name == "legacy-qgc"
    assert not hasattr(public, "token_sha256")
    assert records[0].token_sha256 == hash_bearer_token("legacy-secret")


@pytest.mark.parametrize("duplicate_field", ["token_id", "token_sha256"])
def test_store_rejects_duplicate_token_identity(tmp_path, duplicate_field):
    path = tmp_path / "tokens.json"
    first = make_token_record(
        token_id="first",
        plaintext_token="first-secret",
        scopes=[STATUS_READ],
    )
    second = make_token_record(
        token_id="second",
        plaintext_token="second-secret",
        scopes=[STATUS_READ],
    )
    second[duplicate_field] = first[duplicate_field]
    path.write_text(json.dumps({"tokens": [first, second]}), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(BearerTokenValidationError, match="Duplicate"):
        BearerTokenStore(path).load_snapshot()


def test_runtime_hot_publishes_create_and_revocation(tmp_path):
    path = tmp_path / "tokens.json"
    store = BearerTokenStore(path)
    runtime = _runtime(path, store)

    created = runtime.create_bearer_token(
        display_name="QGC video",
        scopes=[MEDIA_READ],
        subject="qgc",
        expires_at=datetime.now(timezone.utc) + timedelta(days=90),
    )
    plaintext = created.plaintext_token
    assert plaintext is not None

    principal, reason = runtime.principal_from_authorization_header(
        f"Bearer {plaintext}"
    )
    assert reason is None
    assert principal.kind == APIPrincipalKind.BEARER
    assert runtime.principal_is_active(principal) is True

    revoked = runtime.revoke_bearer_token(created.record.token_id)
    assert revoked.record.state == "revoked"
    assert runtime.principal_is_active(principal) is False
    rejected, reason = runtime.principal_from_authorization_header(
        f"Bearer {plaintext}"
    )
    assert rejected.kind == APIPrincipalKind.ANONYMOUS
    assert reason == "inactive_bearer_token"


def test_runtime_reloads_disk_after_ambiguous_token_write_failure(tmp_path):
    path = tmp_path / "tokens.json"
    real_store = BearerTokenStore(path)

    class CommitThenFailStore:
        mutation_lock = threading.RLock()
        last_plaintext = None

        def create_token(self, *args, **kwargs):
            result = real_store.create_token(*args, **kwargs)
            self.last_plaintext = result.plaintext_token
            raise BearerTokenPersistenceError("durability acknowledgement failed")

        def load_snapshot(self, *, allow_missing=False):
            return real_store.load_snapshot(allow_missing=allow_missing)

    store = CommitThenFailStore()
    runtime = _runtime(path, store)

    with pytest.raises(BearerTokenPersistenceError, match="durability"):
        runtime.create_bearer_token(
            display_name="QGC video",
            scopes=[MEDIA_READ],
            subject="qgc",
            expires_at=None,
        )

    principal, reason = runtime.principal_from_authorization_header(
        f"Bearer {store.last_plaintext}"
    )
    assert reason is None
    assert principal.kind == APIPrincipalKind.BEARER


def test_runtime_fails_closed_when_token_store_cannot_be_reconciled(tmp_path):
    path = tmp_path / "tokens.json"

    class UnreadableStore:
        mutation_lock = threading.RLock()

        def create_token(self, *args, **kwargs):
            raise BearerTokenPersistenceError("durability state unknown")

        def load_snapshot(self, *, allow_missing=False):
            raise BearerTokenPersistenceError("token store unavailable")

    existing_secret = "existing-secret"
    record = make_token_record(
        token_id="existing",
        plaintext_token=existing_secret,
        scopes=[MEDIA_READ],
    )
    path.write_text(json.dumps({"tokens": [record]}), encoding="utf-8")
    path.chmod(0o600)
    records = BearerTokenStore(path).load_snapshot()
    runtime = APIAuthRuntime(
        mode=API_AUTH_MODE_BROWSER_SESSION,
        bearer_tokens_by_hash=records.records_by_hash,
        token_file=path,
        token_store=UnreadableStore(),
        users_by_username={
            "admin": make_browser_user_record(
                username="admin",
                plaintext_password="admin-password",
                role="admin",
            )
        },
    )

    with pytest.raises(BearerTokenPersistenceError, match="durability"):
        runtime.create_bearer_token(
            display_name="QGC video",
            scopes=[MEDIA_READ],
            subject="qgc",
            expires_at=None,
        )

    principal, reason = runtime.principal_from_authorization_header(
        f"Bearer {existing_secret}"
    )
    assert principal.kind == APIPrincipalKind.ANONYMOUS
    assert reason == "invalid_bearer_token"
