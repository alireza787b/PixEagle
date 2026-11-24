"""Managed client migration never imports the unrelated native binding."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def policy(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/setup/mavsdk_client_policy.py"
    spec = importlib.util.spec_from_file_location("mavsdk_client_policy_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.importlib, "import_module", Mock())
    return module


def test_missing_new_client_prevents_old_client_removal(policy, monkeypatch):
    policy.importlib.import_module.side_effect = ImportError("missing maintained client")
    run = Mock()
    monkeypatch.setattr(policy.subprocess, "run", run)
    with pytest.raises(ImportError):
        policy.reconcile(migrate=True)
    run.assert_not_called()


def test_old_client_requires_managed_migration(policy, monkeypatch):
    monkeypatch.setattr(policy.metadata, "version", lambda _: "3.15.3")
    with pytest.raises(RuntimeError, match="Retired"):
        policy.reconcile()


def test_migration_removes_old_distribution_and_verifies_result(policy, monkeypatch):
    state = [True]
    monkeypatch.setattr(policy, "legacy_client_present", lambda: state[0])
    run = Mock(side_effect=lambda *args, **kwargs: state.__setitem__(0, False))
    monkeypatch.setattr(policy.subprocess, "run", run)
    policy.reconcile(migrate=True)
    assert run.call_args.args[0][-3:] == ["uninstall", "-y", "mavsdk"]
    assert run.call_args.kwargs["check"] is True
    policy.importlib.import_module.assert_called_once_with("mavsdk_grpc")


def test_native_binding_is_independent_and_not_removed(policy, monkeypatch):
    monkeypatch.setattr(policy.metadata, "version", lambda _: "4.2.0")
    run = Mock()
    monkeypatch.setattr(policy.subprocess, "run", run)
    policy.reconcile(migrate=True)
    run.assert_not_called()


def test_failed_removal_is_not_reported_as_reconciled(policy, monkeypatch):
    monkeypatch.setattr(policy, "legacy_client_present", lambda: True)
    monkeypatch.setattr(policy.subprocess, "run", Mock())
    with pytest.raises(RuntimeError, match="not removed"):
        policy.reconcile(migrate=True)
