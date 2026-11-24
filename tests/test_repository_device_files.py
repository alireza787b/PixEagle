"""Exercise normal Git staging with only the repository's published ignore rules."""

import shutil
import subprocess
from pathlib import Path


def test_staging_device_checkout_excludes_operator_files(tmp_path):
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    for rule_file in (".gitignore", "dashboard/.gitignore"):
        target = tmp_path / rule_file
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rule_file, target)

    public = {
        ".gitignore",
        "dashboard/.gitignore",
        "configs/config_default.yaml",
        "configs/config_schema.yaml",
        "dashboard/package.json",
        "dashboard/package-lock.json",
        ".env.example",
    }
    private = {
        "configs/config.yaml",
        "configs/backups/previous.yaml",
        "configs/secrets/session.json",
        "dashboard/.env",
        "dashboard/.env.production.local",
        "dashboard/backups/previous.env",
        ".env.local",
        "logs/security_audit.jsonl",
        ".pixeagle_runtime/updates/job/previous.yaml",
        "recordings/bench.mp4",
        "private-profile/setup.yaml",
        "PixEagle-profiles-2026-11-24/all-parameters.csv",
        "pixeagle-backups/recovery.bundle",
        "PixEagle-config-backup-20261124",
        "configs/private-config.yaml",
        "private-overrides.yaml",
        "pixeagle_config_2026-11-24T07-15-00.yaml",
        "pixeagle_config_changes_2026-11-24T07-15-00.yaml",
        "temp/credentials.json",
        "initial-credentials.json",
        "capture.ulg",
        "archive/capture.tlog",
        "raspberry-pi-image/backup.img",
        "pixeagle-pi5-backup.img.zst",
    }
    for name in private | public:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    empty_excludes = tmp_path / ".git" / "empty-excludes"
    empty_excludes.touch()
    git = ["git", "-C", str(tmp_path), "-c", f"core.excludesFile={empty_excludes}"]
    subprocess.run([*git, "add", "--all"], check=True)
    staged = subprocess.check_output([*git, "ls-files", "-z"]).decode().split("\0")
    assert set(staged[:-1]) == public
