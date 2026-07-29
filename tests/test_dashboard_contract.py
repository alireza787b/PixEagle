"""Focused tests for the cross-platform dashboard cache contract CLI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT = PROJECT_ROOT / "scripts" / "lib" / "dashboard_contract.js"
NODE = shutil.which("node")
NPM = shutil.which("npm")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required")


def _run_contract(
    command: str,
    dashboard: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            NODE,
            str(CONTRACT),
            command,
            str(dashboard),
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _dependency_tree(tmp_path: Path) -> Path:
    dashboard = tmp_path / "dashboard with spaces"
    (dashboard / "node_modules").mkdir(parents=True)
    (dashboard / "package.json").write_text(
        '{"name":"dashboard","version":"1.0.0"}\n',
        encoding="utf-8",
    )
    (dashboard / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "dashboard",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": {
                        "name": "dashboard",
                        "version": "1.0.0",
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (dashboard / ".npmrc").write_text("fund=false\n", encoding="utf-8")
    (tmp_path / ".nvmrc").write_text("24\n", encoding="utf-8")
    return dashboard


def _build_tree(tmp_path: Path) -> tuple[Path, Path]:
    dashboard = tmp_path / "dashboard with spaces"
    (dashboard / "src").mkdir(parents=True)
    (dashboard / "public").mkdir()
    (dashboard / "src" / "index.js").write_text(
        "export default 1;\n",
        encoding="utf-8",
    )
    (dashboard / "public" / "index.html").write_text(
        "<main></main>\n",
        encoding="utf-8",
    )
    (dashboard / "package.json").write_text("{}\n", encoding="utf-8")
    (dashboard / "package-lock.json").write_text(
        '{"lockfileVersion":3}\n',
        encoding="utf-8",
    )
    node_version = tmp_path / ".nvmrc"
    node_version.write_text("24\n", encoding="utf-8")
    return dashboard, node_version


def _complete_build(dashboard: Path) -> None:
    build = dashboard / "build"
    (build / "static" / "js").mkdir(parents=True)
    (build / "index.html").write_text("<main></main>\n", encoding="utf-8")
    (build / "static" / "js" / "main.js").write_text(
        "console.log('ready');\n",
        encoding="utf-8",
    )
    (build / "asset-manifest.json").write_text(
        json.dumps(
            {
                "files": {"main.js": "./static/js/main.js"},
                "entrypoints": ["static/js/main.js"],
            }
        ),
        encoding="utf-8",
    )


def test_dependency_fingerprint_preserves_manifest_and_runtime_contract(tmp_path):
    dashboard = _dependency_tree(tmp_path)
    node_version = dashboard.parent / ".nvmrc"

    result = _run_contract(
        "dependency-fingerprint",
        dashboard,
        str(node_version),
    )

    assert result.returncode == 0, result.stderr
    runtime = subprocess.run(
        [
            NODE,
            "-p",
            '`${process.platform}:${process.arch}:abi-${process.versions.modules || "none"}`',
        ],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    hashes = [
        hashlib.sha256((dashboard / name).read_bytes()).hexdigest()
        for name in ("package.json", "package-lock.json", ".npmrc")
    ]
    assert result.stdout.strip() == "_".join([*hashes, runtime])


@pytest.mark.skipif(NPM is None, reason="npm is required")
def test_dependencies_ready_accepts_cross_platform_cache_newline(tmp_path):
    dashboard = _dependency_tree(tmp_path)
    node_version = dashboard.parent / ".nvmrc"
    fingerprint = _run_contract(
        "dependency-fingerprint",
        dashboard,
        str(node_version),
    )
    assert fingerprint.returncode == 0, fingerprint.stderr
    cache = dashboard / ".pixeagle_cache" / "deps_hash"
    cache.parent.mkdir()
    cache.write_bytes(f"{fingerprint.stdout.strip()}\r\n".encode())

    ready = _run_contract("dependencies-ready", dashboard, str(node_version))

    assert ready.returncode == 0, ready.stderr
    assert ready.stdout == "true\n"

    (dashboard / "package.json").write_text(
        '{"name":"dashboard","version":"2.0.0"}\n',
        encoding="utf-8",
    )
    stale = _run_contract("dependencies-ready", dashboard, str(node_version))
    assert stale.returncode == 1
    assert stale.stdout == "false\n"


def test_build_fingerprint_is_stable_and_sensitive_to_inputs(tmp_path):
    dashboard, node_version = _build_tree(tmp_path)
    arguments = (str(node_version),)

    first = _run_contract("build-fingerprint", dashboard, *arguments)
    second = _run_contract("build-fingerprint", dashboard, *arguments)

    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert len(first.stdout.strip()) == 64
    assert set(first.stdout.strip()) <= set("0123456789abcdef")

    (dashboard / "src" / "index.js").write_text(
        "export default 2;\n",
        encoding="utf-8",
    )
    changed = _run_contract("build-fingerprint", dashboard, *arguments)
    assert changed.returncode == 0, changed.stderr
    assert changed.stdout != first.stdout


def test_build_complete_reports_machine_readable_result(tmp_path):
    dashboard, _ = _build_tree(tmp_path)
    _complete_build(dashboard)

    complete = _run_contract("build-complete", dashboard)

    assert complete.returncode == 0, complete.stderr
    assert complete.stdout == "true\n"

    (dashboard / "build" / "static" / "js" / "main.js").unlink()
    incomplete = _run_contract("build-complete", dashboard)
    assert incomplete.returncode == 1
    assert incomplete.stdout == "false\n"
    assert "missing referenced asset" in incomplete.stderr


def test_build_complete_rejects_windows_absolute_manifest_path_on_every_os(
    tmp_path,
):
    dashboard, _ = _build_tree(tmp_path)
    _complete_build(dashboard)
    manifest = dashboard / "build" / "asset-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "files": {"main.js": "./static/js/main.js"},
                "entrypoints": [r"C:\outside\main.js"],
            }
        ),
        encoding="utf-8",
    )

    result = _run_contract("build-complete", dashboard)

    assert result.returncode == 1
    assert result.stdout == "false\n"
    assert "reference is not relative" in result.stderr
