"""Focused browser-user persistence and runtime-mutation contracts."""

from __future__ import annotations

import os
import threading

import pytest

import classes.browser_user_store as browser_user_store
from classes.api_auth_runtime import API_AUTH_MODE_BROWSER_SESSION, APIAuthRuntime
from classes.browser_user_store import (
    BrowserUserInvariantError,
    BrowserUserPersistenceError,
    BrowserUserStore,
    make_browser_user_record,
    verify_password_pbkdf2_sha256,
)


def _create_store(tmp_path, *records):
    path = tmp_path / "browser-users.json"
    store = BrowserUserStore(path)
    store.replace_all(records, create_if_missing=True, backup=False)
    return path, store


def _runtime(path, store):
    snapshot = store.load_snapshot()
    return APIAuthRuntime(
        mode=API_AUTH_MODE_BROWSER_SESSION,
        users_by_username=snapshot.records_by_username,
        user_file=path,
        user_store=store,
    )


def test_operator_only_store_remains_valid_for_host_managed_deployments(tmp_path):
    path, store = _create_store(
        tmp_path,
        make_browser_user_record(
            username="operator",
            plaintext_password="old-password",
            role="operator",
        ),
    )

    result = store.update_user(
        "operator",
        plaintext_password="new-password",
        backup=False,
    )

    assert result.record is not None
    assert result.record.role == "operator"
    record = store.load_snapshot().records_by_username["operator"]
    assert verify_password_pbkdf2_sha256(
        password="new-password",
        encoded=record.password_pbkdf2_sha256,
    )
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory-mode contract")
def test_store_rejects_group_or_other_writable_parent(tmp_path):
    unsafe_parent = tmp_path / "unsafe"
    unsafe_parent.mkdir(mode=0o700)
    unsafe_parent.chmod(0o777)
    store = BrowserUserStore(unsafe_parent / "browser-users.json")

    try:
        with pytest.raises(BrowserUserPersistenceError, match="writable by group"):
            store.replace_all(
                [
                    make_browser_user_record(
                        username="admin",
                        plaintext_password="admin-password",
                        role="admin",
                    )
                ],
                create_if_missing=True,
                backup=False,
            )
    finally:
        unsafe_parent.chmod(0o700)


def test_mutations_preserve_the_last_enabled_admin_once_present(tmp_path):
    _path, store = _create_store(
        tmp_path,
        make_browser_user_record(
            username="admin",
            plaintext_password="admin-password",
            role="admin",
        ),
        make_browser_user_record(
            username="operator",
            plaintext_password="operator-password",
            role="operator",
        ),
    )

    with pytest.raises(BrowserUserInvariantError, match="administrator"):
        store.update_user("admin", role="operator", backup=False)
    with pytest.raises(BrowserUserInvariantError, match="administrator"):
        store.update_user("admin", enabled=False, backup=False)
    with pytest.raises(BrowserUserInvariantError, match="administrator"):
        store.delete_user("admin", backup=False)

    store.create_user(
        username="backup-admin",
        plaintext_password="backup-password",
        role="admin",
        backup=False,
    )
    result = store.update_user("admin", role="operator", backup=False)
    assert result.record is not None
    assert result.record.role == "operator"


def test_runtime_admin_update_publishes_snapshot_and_revokes_target_sessions(tmp_path):
    path, store = _create_store(
        tmp_path,
        make_browser_user_record(
            username="admin",
            plaintext_password="admin-password",
            role="admin",
        ),
        make_browser_user_record(
            username="operator",
            plaintext_password="operator-password",
            role="operator",
        ),
    )
    runtime = _runtime(path, store)
    admin_session = runtime.create_session_for_user(runtime.users_by_username["admin"])
    operator_session = runtime.create_session_for_user(
        runtime.users_by_username["operator"]
    )

    result, revoked = runtime.update_browser_user("operator", role="viewer")

    assert result.record is not None
    assert result.record.role == "viewer"
    assert revoked == 1
    assert runtime.session_store.get(operator_session.session_id) is None
    assert runtime.session_store.get(admin_session.session_id) is not None
    assert runtime.users_by_username["operator"].role == "viewer"
    assert store.load_snapshot().records_by_username["operator"].role == "viewer"


def test_self_password_change_replaces_all_sessions_in_operator_only_store(tmp_path):
    path, store = _create_store(
        tmp_path,
        make_browser_user_record(
            username="operator",
            plaintext_password="old-password",
            role="operator",
        ),
    )
    runtime = _runtime(path, store)
    first = runtime.create_session_for_user(runtime.users_by_username["operator"])
    second = runtime.create_session_for_user(runtime.users_by_username["operator"])

    changed = runtime.change_browser_user_password(
        username="operator",
        current_password="old-password",
        new_password="new-password",
    )

    assert changed is not None
    _result, replacement, revoked = changed
    assert revoked == 2
    assert runtime.session_store.get(first.session_id) is None
    assert runtime.session_store.get(second.session_id) is None
    assert runtime.session_store.get(replacement.session_id) is not None
    assert runtime.authenticate_user(
        username="operator",
        password="old-password",
    ) is None
    assert runtime.authenticate_user(
        username="operator",
        password="new-password",
    ) is not None


def test_runtime_reloads_disk_and_revokes_all_after_ambiguous_write_failure(tmp_path):
    path, real_store = _create_store(
        tmp_path,
        make_browser_user_record(
            username="admin",
            plaintext_password="admin-password",
            role="admin",
        ),
        make_browser_user_record(
            username="operator",
            plaintext_password="operator-password",
            role="operator",
        ),
    )

    class CommitThenFailStore:
        mutation_lock = threading.RLock()

        def load_snapshot(self):
            return real_store.load_snapshot()

        def update_user(self, *args, **kwargs):
            real_store.update_user(*args, **kwargs)
            raise BrowserUserPersistenceError("durability acknowledgement failed")

    runtime = _runtime(path, CommitThenFailStore())
    runtime.create_session_for_user(runtime.users_by_username["admin"])
    runtime.create_session_for_user(runtime.users_by_username["operator"])

    with pytest.raises(BrowserUserPersistenceError, match="durability"):
        runtime.update_browser_user("operator", role="viewer")

    assert runtime.users_by_username["operator"].role == "viewer"
    assert runtime.session_store._records == {}


def test_runtime_disables_login_when_persistence_reconciliation_cannot_read_store(
    tmp_path,
):
    path, real_store = _create_store(
        tmp_path,
        make_browser_user_record(
            username="admin",
            plaintext_password="admin-password",
            role="admin",
        ),
    )

    class UnreadableAfterFailureStore:
        mutation_lock = threading.RLock()

        def load_snapshot(self):
            raise BrowserUserPersistenceError("credential store unavailable")

        def update_user(self, *args, **kwargs):
            raise BrowserUserPersistenceError("durability state unknown")

    snapshot = real_store.load_snapshot()
    runtime = APIAuthRuntime(
        mode=API_AUTH_MODE_BROWSER_SESSION,
        users_by_username=snapshot.records_by_username,
        user_file=path,
        user_store=UnreadableAfterFailureStore(),
    )
    session = runtime.create_session_for_user(runtime.users_by_username["admin"])

    with pytest.raises(BrowserUserPersistenceError, match="durability"):
        runtime.update_browser_user("admin", role="admin")

    assert runtime.users_by_username == {}
    assert runtime.session_store.get(session.session_id) is None
    assert runtime.authenticate_user(
        username="admin",
        password="admin-password",
    ) is None


def test_store_retains_backup_when_directory_fsync_fails_after_live_replace(
    tmp_path,
    monkeypatch,
):
    path, store = _create_store(
        tmp_path,
        make_browser_user_record(
            username="admin",
            plaintext_password="admin-password",
            role="admin",
        ),
        make_browser_user_record(
            username="operator",
            plaintext_password="operator-password",
            role="operator",
        ),
    )
    real_fsync_directory = browser_user_store._fsync_directory
    calls = 0

    def fail_after_live_replace(parent):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected directory fsync failure")
        return real_fsync_directory(parent)

    monkeypatch.setattr(
        browser_user_store,
        "_fsync_directory",
        fail_after_live_replace,
    )

    with pytest.raises(BrowserUserPersistenceError, match="atomically write"):
        store.update_user("operator", role="viewer")

    assert store.load_snapshot().records_by_username["operator"].role == "viewer"
    backups = sorted(tmp_path.glob("browser-users.json.backup.*"))
    assert len(backups) == 1
    backup_snapshot = BrowserUserStore(backups[0]).load_snapshot()
    assert backup_snapshot.records_by_username["operator"].role == "operator"
