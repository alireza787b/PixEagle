#!/usr/bin/env python3
"""Report config update state without exposing values or mutating runtime config."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report defaults and registered-retirement status for config.yaml.",
    )
    baseline_group = parser.add_mutually_exclusive_group()
    baseline_group.add_argument(
        "--initialize-baseline",
        action="store_true",
        help="Persist current defaults only when no update baseline exists.",
    )
    baseline_group.add_argument(
        "--replace-baseline",
        action="store_true",
        help=(
            "Explicitly replace the update baseline after reviewing all pending "
            "changed defaults."
        ),
    )
    baseline_group.add_argument(
        "--initialize-baseline-from",
        type=Path,
        metavar="YAML",
        help=(
            "Initialize a missing baseline from an owner-controlled pre-update "
            "defaults file; an existing baseline is preserved."
        ),
    )
    baseline_group.add_argument(
        "--validate-staged-baseline",
        type=Path,
        metavar="YAML",
        help="Validate a staged defaults file without changing config lifecycle state.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the redacted machine-readable report.",
    )
    return parser.parse_args()


def _validate_windows_owner_only_acl(source_path: Path) -> None:
    """Fail closed unless a Windows file has one protected owner-only ACL rule."""
    shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if shell is None:
        raise ValueError("PowerShell is required to validate staged defaults ACLs.")
    script = r"""
$ErrorActionPreference = 'Stop'
$path = $args[0]
$item = Get-Item -LiteralPath $path -Force
if ($item.PSIsContainer -or
    (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
    throw 'staged defaults must be a regular non-reparse-point file'
}
$currentSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$acl = Get-Acl -LiteralPath $path
$ownerSid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier])
$rules = @($acl.GetAccessRules(
    $true,
    $true,
    [System.Security.Principal.SecurityIdentifier]
))
if (-not $acl.AreAccessRulesProtected -or
    $ownerSid.Value -ne $currentSid.Value -or
    $rules.Count -ne 1 -or
    $rules[0].IsInherited -or
    $rules[0].AccessControlType -ne
        [System.Security.AccessControl.AccessControlType]::Allow -or
    $rules[0].IdentityReference.Value -ne $currentSid.Value -or
    (($rules[0].FileSystemRights -band
        [System.Security.AccessControl.FileSystemRights]::FullControl) -ne
        [System.Security.AccessControl.FileSystemRights]::FullControl)) {
    throw 'staged defaults ACL must be protected and grant only the owner full control'
}
"""
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command", script, str(source_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(
            "Staged defaults baseline failed Windows ACL validation"
            + (f": {detail}" if detail else ".")
        )


def _is_reparse_point(path_stat: os.stat_result) -> bool:
    attributes = getattr(path_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(reparse_flag and attributes & reparse_flag)


def _load_staged_defaults(source_path: Path) -> tuple[dict, str]:
    """Load an owner-controlled staged defaults file without following links."""
    descriptor = None
    try:
        path_stat = os.lstat(source_path)
        if not stat.S_ISREG(path_stat.st_mode) or _is_reparse_point(path_stat):
            raise ValueError("Staged defaults baseline must be a regular non-symlink file.")
        open_flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            open_flags |= os.O_NOFOLLOW
        descriptor = os.open(source_path, open_flags)
        source_stat = os.fstat(descriptor)
        if (path_stat.st_dev, path_stat.st_ino) != (source_stat.st_dev, source_stat.st_ino):
            raise ValueError("Staged defaults baseline changed while it was opened.")
        if os.name == "nt":
            _validate_windows_owner_only_acl(source_path)
            verified_stat = os.lstat(source_path)
            if (verified_stat.st_dev, verified_stat.st_ino) != (
                source_stat.st_dev,
                source_stat.st_ino,
            ):
                raise ValueError("Staged defaults baseline changed during ACL validation.")
    except ValueError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ValueError(f"Could not open staged defaults baseline safely: {exc}") from exc

    if not stat.S_ISREG(source_stat.st_mode):
        os.close(descriptor)
        raise ValueError("Staged defaults baseline must be a regular non-symlink file.")
    if source_stat.st_size <= 0:
        os.close(descriptor)
        raise ValueError("Staged defaults baseline must not be empty.")
    if os.name != "nt":
        if source_stat.st_uid != os.geteuid():
            os.close(descriptor)
            raise ValueError("Staged defaults baseline must be owned by the current user.")
        if stat.S_IMODE(source_stat.st_mode) & 0o077:
            os.close(descriptor)
            raise ValueError("Staged defaults baseline permissions must be owner-only.")

    try:
        with os.fdopen(descriptor, "rb", closefd=True) as source_file:
            descriptor = None
            source_bytes = source_file.read()
        staged_defaults = yaml.safe_load(source_bytes)
    except yaml.YAMLError as exc:
        raise ValueError("Could not parse staged defaults baseline safely.") from exc
    except OSError as exc:
        raise ValueError(f"Could not read staged defaults baseline: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(staged_defaults, dict) or not staged_defaults:
        raise ValueError("Staged defaults baseline must contain a non-empty YAML mapping.")
    return staged_defaults, hashlib.sha256(source_bytes).hexdigest()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    if args.validate_staged_baseline is not None:
        source_path = args.validate_staged_baseline.expanduser()
        if not source_path.is_absolute():
            source_path = project_root / source_path
        try:
            _load_staged_defaults(source_path)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if not args.json:
            print("Staged config defaults baseline is valid.")
        return 0

    from classes.config_sync import build_defaults_sync_report
    from classes.config_service import ConfigService

    try:
        service = ConfigService(project_root=project_root)
    except Exception as exc:
        print(f"Could not load config lifecycle state: {exc}", file=sys.stderr)
        return 2

    try:
        if args.initialize_baseline_from is not None:
            source_path = args.initialize_baseline_from.expanduser()
            if not source_path.is_absolute():
                source_path = project_root / source_path
            staged_defaults, source_digest = _load_staged_defaults(source_path)
            had_baseline = bool(service.get_sync_meta().get("defaults_snapshot"))
            if not service.initialize_defaults_snapshot_from(
                staged_defaults,
                provenance="pre_update_staged_defaults",
                source_digest=source_digest,
            ):
                print("Could not initialize the staged config defaults baseline.", file=sys.stderr)
                return 2
            if not args.json:
                print(
                    "Existing config defaults baseline preserved."
                    if had_baseline
                    else "Pre-update config defaults baseline initialized."
                )
        elif args.initialize_baseline:
            had_baseline = bool(service.get_sync_meta().get("defaults_snapshot"))
            if not service.initialize_defaults_snapshot():
                print("Could not initialize the config defaults baseline.", file=sys.stderr)
                return 2
            if had_baseline and not args.json:
                print("Existing config defaults baseline preserved.")
        elif args.replace_baseline:
            if not service.refresh_defaults_snapshot():
                print("Could not replace the config defaults baseline.", file=sys.stderr)
                return 2
            if not args.json:
                print("Config defaults baseline replaced after explicit review.")
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        report = build_defaults_sync_report(service)
    except Exception as exc:
        print(f"Could not report config lifecycle state: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    counts = report["counts"]
    print(
        "Config update status: "
        f"{counts['new']} new, {counts['changed']} changed defaults, "
        f"{counts['retired']} registered retirements, "
        f"{counts['extensions']} preserved extensions."
    )
    if counts["actionable"]:
        print("Review and preview pending config actions in Dashboard > Settings > Config Sync.")
    if counts["extensions"]:
        print("Unmanaged extension paths are preserved and are never auto-removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
