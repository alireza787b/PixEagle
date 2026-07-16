import importlib.util
from pathlib import Path
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "setup" / "check-managed-sih.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_managed_sih", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _host_probe(container_state="absent", ownership=False):
    return {
        "docker_cli_available": True,
        "docker_daemon_accessible": True,
        "image_available": True,
        "container_state": container_state,
        "ownership_verified": ownership,
    }


def _browser_config(module, tmp_path, *, auth_mode="browser_session"):
    user_file = tmp_path / "users.json"
    from classes.api_auth_runtime import make_user_record

    user_file.write_text(
        __import__("json").dumps(
            {
                "users": [
                    make_user_record(
                        username="admin",
                        plaintext_password="test-password",
                        role="admin",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    user_file.chmod(0o600)
    audit_path = tmp_path / "audit.jsonl"
    config = {
        "Debugging": {"ENABLE_MANAGED_SIH": True},
        "Streaming": {
            "API_AUTH_MODE": auth_mode,
            "API_SESSION_USER_FILE": str(user_file),
            "API_SECURITY_AUDIT_ENABLED": True,
            "API_SECURITY_AUDIT_LOG_PATH": str(audit_path),
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def test_doctor_reports_ready_without_mutating_runtime(monkeypatch, tmp_path):
    module = _load_module()
    config_path = _browser_config(module, tmp_path)
    ledger_path = tmp_path / "managed_sih_actions.json"
    monkeypatch.setattr(module, "probe_managed_sih", lambda *_args, **_kwargs: _host_probe())

    report = module.collect_checks(config_path, ledger_path=ledger_path)

    assert report["ready"] is True
    assert report["summary"]["fail"] == 0
    assert report["summary"]["warn"] == 1
    assert not ledger_path.exists()
    assert not (tmp_path / "audit.jsonl").exists()


def test_doctor_rejects_local_compat_even_when_other_prerequisites_pass(
    monkeypatch, tmp_path
):
    module = _load_module()
    config_path = _browser_config(module, tmp_path, auth_mode="local_compat")
    monkeypatch.setattr(module, "probe_managed_sih", lambda *_args, **_kwargs: _host_probe())

    report = module.collect_checks(
        config_path,
        ledger_path=tmp_path / "managed_sih_actions.json",
    )

    checks = {item["id"]: item for item in report["checks"]}
    assert report["ready"] is False
    assert checks["attributable_admin_auth"]["status"] == "fail"
    assert "local_compat" in checks["attributable_admin_auth"]["remediation"]


def test_doctor_rejects_unowned_container_name_collision(monkeypatch, tmp_path):
    module = _load_module()
    config_path = _browser_config(module, tmp_path)
    monkeypatch.setattr(
        module,
        "probe_managed_sih",
        lambda *_args, **_kwargs: _host_probe("conflict", False),
    )

    report = module.collect_checks(
        config_path,
        ledger_path=tmp_path / "managed_sih_actions.json",
    )

    checks = {item["id"]: item for item in report["checks"]}
    assert report["ready"] is False
    assert checks["managed_container_slot"]["status"] == "fail"
    assert "Do not stop" in checks["managed_container_slot"]["remediation"]


def test_doctor_accepts_running_owned_container_for_recovery(monkeypatch, tmp_path):
    module = _load_module()
    config_path = _browser_config(module, tmp_path)
    monkeypatch.setattr(
        module,
        "probe_managed_sih",
        lambda *_args, **_kwargs: _host_probe("running", True),
    )

    report = module.collect_checks(
        config_path,
        ledger_path=tmp_path / "managed_sih_actions.json",
    )

    checks = {item["id"]: item for item in report["checks"]}
    assert report["ready"] is True
    assert checks["managed_container_slot"]["status"] == "pass"


def test_writable_target_rejects_symlink_without_following_it(tmp_path):
    module = _load_module()
    target = tmp_path / "actual.jsonl"
    target.write_text("", encoding="utf-8")
    link = tmp_path / "audit.jsonl"
    link.symlink_to(target)

    ready, detail = module._safe_writable_target(link)

    assert ready is False
    assert "symbolic link" in detail
