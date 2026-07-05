#!/usr/bin/env python3
"""Manage PixEagle browser-session users in an external JSON file.

This is an offline maintenance tool. It intentionally does not expose a remote
admin API or revoke already-running in-memory sessions; restart PixEagle after
changing the active API_SESSION_USER_FILE when immediate enforcement matters.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import stat
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from classes.api_auth_runtime import (  # noqa: E402
    APIAuthConfigurationError,
    APIUserRecord,
    load_user_records,
    make_user_record,
)
from classes.api_security_types import ROLE_SCOPES  # noqa: E402


class BrowserUserToolError(ValueError):
    """Raised for operator-correctable browser-user CLI errors."""


def _normalize_username(value: str) -> str:
    username = str(value or "").strip().lower()
    if not username:
        raise BrowserUserToolError("Username must not be empty")
    return username


def _normalize_role(value: str) -> str:
    role = str(value or "").strip().lower()
    if role not in ROLE_SCOPES:
        allowed = ", ".join(sorted(ROLE_SCOPES))
        raise BrowserUserToolError(f"Unsupported role {value!r}; expected one of: {allowed}")
    return role


def _records_to_payload(records: list[APIUserRecord]) -> dict[str, list[dict[str, Any]]]:
    return {"users": [asdict(record) for record in records]}


def _load_records(path: Path, *, allow_missing: bool = False) -> list[APIUserRecord]:
    if allow_missing and not path.exists():
        return []
    try:
        return list(load_user_records(path))
    except APIAuthConfigurationError as exc:
        raise BrowserUserToolError(str(exc)) from exc


def _backup_path(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return path.with_name(f"{path.name}.backup.{stamp}")


def _copy_backup(path: Path) -> Path:
    backup = _backup_path(path)
    suffix = 0
    while backup.exists():
        suffix += 1
        backup = path.with_name(f"{path.name}.backup.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.{suffix}")
    backup.write_bytes(path.read_bytes())
    os.chmod(backup, 0o600)
    return backup


def _write_payload(path: Path, records: list[APIUserRecord], *, backup: bool) -> Path | None:
    path = path.expanduser().resolve()
    if path.exists() and path.is_symlink():
        raise BrowserUserToolError(f"Refusing to write symlink user file: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    backup_written: Path | None = None
    if path.exists() and backup:
        backup_written = _copy_backup(path)

    payload = json.dumps(_records_to_payload(records), indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != 0o600:
            os.chmod(path, 0o600)
    return backup_written


def _find_index(records: list[APIUserRecord], username: str) -> int:
    for index, record in enumerate(records):
        if record.username == username:
            return index
    return -1


def _password_from_args(args: argparse.Namespace) -> tuple[str, bool]:
    if args.generate_password:
        return secrets.token_urlsafe(24), True
    if args.password_file:
        password_path = Path(args.password_file).expanduser()
        try:
            password = password_path.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError) as exc:
            raise BrowserUserToolError(f"Could not read password file: {password_path}") from exc
        if not password:
            raise BrowserUserToolError("Password file first line must not be empty")
        return password, False
    if args.password is not None:
        if not args.password:
            raise BrowserUserToolError("Password must not be empty")
        return args.password, False
    if not sys.stdin.isatty():
        raise BrowserUserToolError(
            "Password is required in non-interactive mode. Use --password, "
            "--password-file, or --generate-password."
        )
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise BrowserUserToolError("Password confirmation did not match")
    if not password:
        raise BrowserUserToolError("Password must not be empty")
    return password, False


def _maybe_write_handoff(
    path_value: str | None,
    *,
    username: str,
    role: str,
    password: str,
    action: str,
) -> Path | None:
    if not path_value:
        return None
    handoff_path = Path(path_value).expanduser().resolve()
    if handoff_path.exists():
        raise BrowserUserToolError(f"Credential handoff file already exists: {handoff_path}")
    handoff_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "username": username,
        "password": password,
        "role": role,
        "action": action,
        "one_time_handoff": True,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    fd, tmp_name = tempfile.mkstemp(prefix=f".{handoff_path.name}.", suffix=".tmp", dir=handoff_path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(payload, tmp_file, indent=2, sort_keys=True)
            tmp_file.write("\n")
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, handoff_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
    return handoff_path


def _print_record_table(records: list[APIUserRecord]) -> None:
    if not records:
        print("No browser-session users found.")
        return
    print(f"{'username':<28} {'role':<10} enabled")
    print(f"{'-' * 28} {'-' * 10} -------")
    for record in records:
        print(f"{record.username:<28} {record.role:<10} {str(record.enabled).lower()}")


def _warn_if_no_enabled_users(records: list[APIUserRecord]) -> None:
    if not any(record.enabled for record in records):
        print(
            "WARNING: no enabled browser-session users remain; browser login "
            "will fail until a user is added or enabled."
        )


def cmd_list(args: argparse.Namespace) -> int:
    records = _load_records(args.file)
    if args.json:
        safe_records = [
            {"username": record.username, "role": record.role, "enabled": record.enabled}
            for record in records
        ]
        print(json.dumps({"users": safe_records}, indent=2, sort_keys=True))
    else:
        _print_record_table(records)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    records = _load_records(args.file)
    enabled = sum(1 for record in records if record.enabled)
    print(f"Verified {len(records)} user record(s); enabled={enabled}; file={args.file}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    username = _normalize_username(args.username)
    role = _normalize_role(args.role)
    records = _load_records(args.file, allow_missing=args.create)
    if _find_index(records, username) >= 0:
        raise BrowserUserToolError(f"User already exists: {username}")
    password, generated = _password_from_args(args)
    record = APIUserRecord(**make_user_record(
        username=username,
        plaintext_password=password,
        role=role,
        enabled=not args.disabled,
    ))
    backup = _write_payload(args.file, [*records, record], backup=not args.no_backup)
    handoff = _maybe_write_handoff(
        args.credential_handoff_file,
        username=username,
        role=role,
        password=password,
        action="add",
    )
    print(f"Added browser-session user: {username} ({role}, enabled={str(record.enabled).lower()})")
    if generated and handoff is None:
        print(f"Generated password for {username}: {password}")
    if handoff is not None:
        print(f"Wrote one-time credential handoff file: {handoff}")
    if backup is not None:
        print(f"Backed up previous user file: {backup}")
    _warn_if_no_enabled_users([*records, record])
    print("Restart PixEagle to force the running auth runtime to reload this file.")
    return 0


def _replace_record(records: list[APIUserRecord], index: int, **changes: Any) -> APIUserRecord:
    current = records[index]
    updated = APIUserRecord(
        username=changes.get("username", current.username),
        role=changes.get("role", current.role),
        password_pbkdf2_sha256=changes.get(
            "password_pbkdf2_sha256",
            current.password_pbkdf2_sha256,
        ),
        enabled=changes.get("enabled", current.enabled),
    )
    records[index] = updated
    return updated


def _existing_index(records: list[APIUserRecord], username: str) -> int:
    index = _find_index(records, username)
    if index < 0:
        raise BrowserUserToolError(f"User not found: {username}")
    return index


def cmd_set_password(args: argparse.Namespace) -> int:
    username = _normalize_username(args.username)
    records = _load_records(args.file)
    index = _existing_index(records, username)
    password, generated = _password_from_args(args)
    password_hash = make_user_record(
        username=username,
        plaintext_password=password,
        role=records[index].role,
        enabled=records[index].enabled,
    )["password_pbkdf2_sha256"]
    updated = _replace_record(records, index, password_pbkdf2_sha256=password_hash)
    backup = _write_payload(args.file, records, backup=not args.no_backup)
    handoff = _maybe_write_handoff(
        args.credential_handoff_file,
        username=username,
        role=updated.role,
        password=password,
        action="set-password",
    )
    print(f"Updated password for browser-session user: {username}")
    if generated and handoff is None:
        print(f"Generated password for {username}: {password}")
    if handoff is not None:
        print(f"Wrote one-time credential handoff file: {handoff}")
    if backup is not None:
        print(f"Backed up previous user file: {backup}")
    print("Restart PixEagle or log out active sessions when immediate enforcement matters.")
    return 0


def cmd_set_role(args: argparse.Namespace) -> int:
    username = _normalize_username(args.username)
    role = _normalize_role(args.role)
    records = _load_records(args.file)
    index = _existing_index(records, username)
    _replace_record(records, index, role=role)
    backup = _write_payload(args.file, records, backup=not args.no_backup)
    print(f"Updated role for browser-session user: {username} -> {role}")
    if backup is not None:
        print(f"Backed up previous user file: {backup}")
    print("Restart PixEagle or log out active sessions when immediate enforcement matters.")
    return 0


def _set_enabled(args: argparse.Namespace, enabled: bool) -> int:
    username = _normalize_username(args.username)
    records = _load_records(args.file)
    index = _existing_index(records, username)
    _replace_record(records, index, enabled=enabled)
    backup = _write_payload(args.file, records, backup=not args.no_backup)
    state = "enabled" if enabled else "disabled"
    print(f"{state.capitalize()} browser-session user: {username}")
    if backup is not None:
        print(f"Backed up previous user file: {backup}")
    _warn_if_no_enabled_users(records)
    print("Restart PixEagle or log out active sessions when immediate enforcement matters.")
    return 0


def cmd_enable(args: argparse.Namespace) -> int:
    return _set_enabled(args, True)


def cmd_disable(args: argparse.Namespace) -> int:
    return _set_enabled(args, False)


def cmd_remove(args: argparse.Namespace) -> int:
    username = _normalize_username(args.username)
    records = _load_records(args.file)
    index = _existing_index(records, username)
    removed = records.pop(index)
    backup = _write_payload(args.file, records, backup=not args.no_backup)
    print(f"Removed browser-session user: {removed.username}")
    if backup is not None:
        print(f"Backed up previous user file: {backup}")
    _warn_if_no_enabled_users(records)
    print("Restart PixEagle or log out active sessions when immediate enforcement matters.")
    return 0


def _add_password_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--password", help="Plaintext password. Avoid shell history in real deployments.")
    group.add_argument("--password-file", help="Read password from first line of this file.")
    group.add_argument("--generate-password", action="store_true", help="Generate and print a one-time password.")
    parser.add_argument(
        "--credential-handoff-file",
        help="Write generated/supplied plaintext credentials once to an owner-only JSON file.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage PixEagle API_AUTH_MODE=browser_session user files.",
    )
    parser.add_argument(
        "--file",
        type=Path,
        required=True,
        help="External API_SESSION_USER_FILE JSON path.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create an owner-only backup before modifying an existing file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List users without password hashes.")
    list_parser.add_argument("--json", action="store_true", help="Print machine-readable summary.")
    list_parser.set_defaults(func=cmd_list)

    verify_parser = subparsers.add_parser("verify", help="Validate the user file.")
    verify_parser.set_defaults(func=cmd_verify)

    add_parser = subparsers.add_parser("add", help="Add a browser-session user.")
    add_parser.add_argument("--username", required=True)
    add_parser.add_argument("--role", default="operator", choices=sorted(ROLE_SCOPES))
    add_parser.add_argument("--disabled", action="store_true", help="Create the user disabled.")
    add_parser.add_argument("--create", action="store_true", help="Create the user file if missing.")
    _add_password_args(add_parser)
    add_parser.set_defaults(func=cmd_add)

    password_parser = subparsers.add_parser("set-password", help="Set a user's password.")
    password_parser.add_argument("--username", required=True)
    _add_password_args(password_parser)
    password_parser.set_defaults(func=cmd_set_password)

    role_parser = subparsers.add_parser("set-role", help="Set a user's role.")
    role_parser.add_argument("--username", required=True)
    role_parser.add_argument("--role", required=True, choices=sorted(ROLE_SCOPES))
    role_parser.set_defaults(func=cmd_set_role)

    enable_parser = subparsers.add_parser("enable", help="Enable a user.")
    enable_parser.add_argument("--username", required=True)
    enable_parser.set_defaults(func=cmd_enable)

    disable_parser = subparsers.add_parser("disable", help="Disable a user.")
    disable_parser.add_argument("--username", required=True)
    disable_parser.set_defaults(func=cmd_disable)

    remove_parser = subparsers.add_parser("remove", help="Remove a user.")
    remove_parser.add_argument("--username", required=True)
    remove_parser.set_defaults(func=cmd_remove)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.file = args.file.expanduser().resolve()
    try:
        return int(args.func(args))
    except BrowserUserToolError as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
