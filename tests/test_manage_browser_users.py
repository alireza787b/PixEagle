"""Tests for the offline browser-session user management CLI."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from classes.api_auth_runtime import load_user_records, verify_password_pbkdf2_sha256


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "manage-browser-users.py"


pytestmark = [pytest.mark.unit]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _extract_generated_password(stdout: str, username: str) -> str:
    match = re.search(rf"Generated password for {re.escape(username)}: (\S+)", stdout)
    assert match, stdout
    return match.group(1)


def test_browser_user_cli_adds_generated_admin_user_without_plaintext(tmp_path):
    user_file = tmp_path / "browser-users.json"

    result = _run_cli(
        "--file",
        str(user_file),
        "add",
        "--create",
        "--username",
        "Admin",
        "--role",
        "admin",
        "--generate-password",
    )

    assert result.returncode == 0, result.stderr
    generated_password = _extract_generated_password(result.stdout, "admin")
    assert user_file.stat().st_mode & 0o777 == 0o600
    raw_payload = json.loads(user_file.read_text(encoding="utf-8"))
    user_record = raw_payload["users"][0]
    assert user_record["username"] == "admin"
    assert user_record["role"] == "admin"
    assert user_record["enabled"] is True
    assert "password" not in user_record
    assert "plaintext_password" not in user_record
    assert generated_password not in user_file.read_text(encoding="utf-8")

    records = load_user_records(user_file)
    assert verify_password_pbkdf2_sha256(
        password=generated_password,
        encoded=records[0].password_pbkdf2_sha256,
    )


def test_browser_user_cli_list_redacts_hashes(tmp_path):
    user_file = tmp_path / "browser-users.json"
    add = _run_cli(
        "--file",
        str(user_file),
        "add",
        "--create",
        "--username",
        "admin",
        "--role",
        "admin",
        "--password",
        "viewer-password",
    )
    assert add.returncode == 0, add.stderr

    table = _run_cli("--file", str(user_file), "list")
    as_json = _run_cli("--file", str(user_file), "list", "--json")

    assert table.returncode == 0
    assert "admin" in table.stdout
    assert "pbkdf2_sha256" not in table.stdout
    assert "viewer-password" not in table.stdout
    assert as_json.returncode == 0
    payload = json.loads(as_json.stdout)
    assert payload == {"users": [{"enabled": True, "role": "admin", "username": "admin"}]}
    assert "pbkdf2_sha256" not in as_json.stdout


def test_browser_user_cli_updates_password_role_enabled_and_remove(tmp_path):
    user_file = tmp_path / "browser-users.json"
    add = _run_cli(
        "--file",
        str(user_file),
        "add",
        "--create",
        "--username",
        "operator",
        "--password",
        "old-password",
    )
    assert add.returncode == 0, add.stderr

    reset = _run_cli(
        "--file",
        str(user_file),
        "set-password",
        "--username",
        "operator",
        "--generate-password",
    )
    assert reset.returncode == 0, reset.stderr
    new_password = _extract_generated_password(reset.stdout, "operator")
    records = load_user_records(user_file)
    assert not verify_password_pbkdf2_sha256(
        password="old-password",
        encoded=records[0].password_pbkdf2_sha256,
    )
    assert verify_password_pbkdf2_sha256(
        password=new_password,
        encoded=records[0].password_pbkdf2_sha256,
    )
    assert list(tmp_path.glob("browser-users.json.backup.*"))

    role = _run_cli(
        "--file",
        str(user_file),
        "set-role",
        "--username",
        "operator",
        "--role",
        "admin",
    )
    assert role.returncode == 0, role.stderr
    assert load_user_records(user_file)[0].role == "admin"

    second_admin = _run_cli(
        "--file",
        str(user_file),
        "add",
        "--username",
        "backup-admin",
        "--role",
        "admin",
        "--password",
        "backup-password",
    )
    assert second_admin.returncode == 0, second_admin.stderr

    disable = _run_cli("--file", str(user_file), "disable", "--username", "operator")
    assert disable.returncode == 0, disable.stderr
    assert next(record for record in load_user_records(user_file) if record.username == "operator").enabled is False

    enable = _run_cli("--file", str(user_file), "enable", "--username", "operator")
    assert enable.returncode == 0, enable.stderr
    assert load_user_records(user_file)[0].enabled is True

    remove = _run_cli("--file", str(user_file), "remove", "--username", "operator")
    assert remove.returncode == 0, remove.stderr
    assert [record.username for record in load_user_records(user_file)] == ["backup-admin"]

    final_disable = _run_cli(
        "--file",
        str(user_file),
        "disable",
        "--username",
        "backup-admin",
    )
    final_remove = _run_cli(
        "--file",
        str(user_file),
        "remove",
        "--username",
        "backup-admin",
    )
    assert final_disable.returncode == 2
    assert "At least one enabled browser-session user" in final_disable.stderr
    assert final_remove.returncode == 2
    assert "At least one enabled browser-session user" in final_remove.stderr


def test_browser_user_cli_can_write_one_time_handoff_file(tmp_path):
    user_file = tmp_path / "browser-users.json"
    handoff_file = tmp_path / "handoff.json"

    result = _run_cli(
        "--file",
        str(user_file),
        "add",
        "--create",
        "--username",
        "admin",
        "--role",
        "admin",
        "--generate-password",
        "--credential-handoff-file",
        str(handoff_file),
    )

    assert result.returncode == 0, result.stderr
    assert "Generated password for admin:" not in result.stdout
    assert handoff_file.stat().st_mode & 0o777 == 0o600
    handoff = json.loads(handoff_file.read_text(encoding="utf-8"))
    assert handoff["username"] == "admin"
    assert handoff["role"] == "admin"
    assert handoff["password"]
    assert handoff["one_time_handoff"] is True
    assert handoff["password"] not in user_file.read_text(encoding="utf-8")


def test_browser_user_cli_fails_closed_for_missing_user_file_without_create(tmp_path):
    user_file = tmp_path / "missing-users.json"

    result = _run_cli(
        "--file",
        str(user_file),
        "add",
        "--username",
        "operator",
        "--password",
        "password",
    )

    assert result.returncode == 2
    assert "does not exist" in result.stderr
    assert not user_file.exists()
