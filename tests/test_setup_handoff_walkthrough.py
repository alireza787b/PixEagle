"""Guards for the PXE-0074 clean setup/update walkthrough harness."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "tools" / "run_setup_handoff_walkthrough.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("run_setup_handoff_walkthrough", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_setup_handoff_plan_is_side_effect_limited():
    tool = _load_tool()

    commands = tool.build_command_plan(
        python_bin=sys.executable,
        include_phase0=True,
        include_sync=True,
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
    assert "sync_clean_worktree_fast_forward_check" in names
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


def test_setup_handoff_plan_only_writes_manifest(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--plan-only",
            "--allow-dirty-source",
            "--skip-phase0",
            "--skip-sync",
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
