"""Guards for the PXE-0074 clean setup/update walkthrough harness."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "tools" / "run_setup_handoff_walkthrough.py"
README = PROJECT_ROOT / "README.md"
INSTALLATION_DOC = PROJECT_ROOT / "docs" / "INSTALLATION.md"


def _load_tool():
    spec = importlib.util.spec_from_file_location("run_setup_handoff_walkthrough", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_setup_handoff_plan_is_side_effect_limited():
    tool = _load_tool()

    assert "scripts/lib/dashboard_dependencies.sh" in tool.REQUIRED_FILES

    commands = tool.build_command_plan(
        python_bin=sys.executable,
        include_phase0=True,
        include_update_check=True,
        include_dashboard=False,
        demo_host="192.168.10.42",
        gcs_host="192.168.10.20",
        public_host="pixeagle.example",
    )
    tool.assert_safe_plan(commands)

    names = {spec.name for spec in commands}
    assert "binary_download_plan" in names
    assert "make_quick_browser_demo_dry_run" in names
    assert "make_quick_browser_demo_cleanup_dry_run" in names
    assert "stopped_runtime_update_dry_run" in names
    assert "config_sync_redacted_status" in names
    assert "schema_check" in names
    assert "minimum_backend_api_tests" in names
    assert "dashboard_npm_ci" not in names

    printable_plan = "\n".join(spec.printable() for spec in commands)
    assert "make init" not in printable_plan
    assert "sudo" not in printable_plan
    assert "service-install" not in printable_plan
    assert "download-binaries.sh --all --dry-run" in printable_plan
    assert "download-binaries.sh --all\n" not in printable_plan

    quick_demo = next(spec for spec in commands if spec.name == "make_quick_browser_demo_dry_run")
    cleanup = next(spec for spec in commands if spec.name == "make_quick_browser_demo_cleanup_dry_run")
    assert "DRY_RUN=1" in quick_demo.command
    assert "START_DEMO=0" in quick_demo.command
    assert "OPEN_FIREWALL=0" in quick_demo.command
    assert "DRY_RUN=1" in cleanup.command
    assert "STOP_DEMO=0" in cleanup.command
    assert "CLOSE_FIREWALL=0" in cleanup.command


def test_git_status_cleanliness_requires_no_file_changes():
    tool = _load_tool()

    assert tool.git_status_stdout_is_clean(
        "## codex/modernization-pxe0040-runtime-20260604...origin/codex/modernization-pxe0040-runtime-20260604\n"
    )
    assert not tool.git_status_stdout_is_clean(
        "## codex/modernization-pxe0040-runtime-20260604\n M README.md\n"
    )
    assert not tool.git_status_stdout_is_clean(
        "## codex/modernization-pxe0040-runtime-20260604\n?? evidence/\n"
    )


def test_command_manifest_uses_portable_relative_log_paths(tmp_path):
    tool = _load_tool()
    checkout = tmp_path / "checkout"
    logs_dir = tmp_path / "evidence" / "logs"
    checkout.mkdir()
    logs_dir.mkdir(parents=True)
    spec = tool.CommandSpec(
        name="portable_paths",
        command=(sys.executable, "-c", "print('ok')"),
    )

    result = tool.run_command(spec, checkout=checkout, logs_dir=logs_dir)

    assert result["passed"] is True
    assert result["stdout_log"] == "logs/portable_paths.stdout.log"
    assert result["stderr_log"] == "logs/portable_paths.stderr.log"
    assert not Path(result["stdout_log"]).is_absolute()
    assert not Path(result["stderr_log"]).is_absolute()


def test_setup_handoff_plan_only_writes_manifest(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--plan-only",
            "--allow-dirty-source",
            "--skip-phase0",
            "--skip-update-check",
            "--artifact-root",
            str(tmp_path),
            "--run-id",
            "plan",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["summary"]["passed"] is True
    assert manifest["summary"]["plan_only"] is True
    assert "Clean-checkout setup/update dry-run" in manifest["metadata"]["claim_boundary"]

    manifest_path = tmp_path / "plan" / "manifest.json"
    assert manifest_path.is_file()
    from_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert from_disk["summary"]["command_count"] == manifest["summary"]["command_count"]
    command_names = {item["name"] for item in from_disk["commands"]}
    assert "make_quick_browser_demo_dry_run" in command_names
    assert "make_quick_browser_demo_cleanup_dry_run" in command_names


def test_handoff_docs_use_installed_project_python():
    for path in (README, INSTALLATION_DOC):
        content = path.read_text(encoding="utf-8")
        assert ".venv/bin/python tools/run_setup_handoff_walkthrough.py" in content
        assert "python3 tools/run_setup_handoff_walkthrough.py" not in content
