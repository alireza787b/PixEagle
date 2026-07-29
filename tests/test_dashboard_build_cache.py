"""Regression tests for the content-addressed dashboard build cache."""

import json
import os
from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HELPER = PROJECT_ROOT / "scripts" / "lib" / "dashboard_build_cache.sh"


def _dashboard_tree(tmp_path: Path) -> tuple[Path, Path]:
    dashboard = tmp_path / "dashboard"
    (dashboard / "src").mkdir(parents=True)
    (dashboard / "public").mkdir()
    (dashboard / "src" / "index.js").write_text("export default 1;\n", encoding="utf-8")
    (dashboard / "public" / "index.html").write_text("<main></main>\n", encoding="utf-8")
    (dashboard / "package.json").write_text('{"scripts":{"build":"react-scripts build"}}\n')
    (dashboard / "package-lock.json").write_text('{"lockfileVersion":3}\n')
    (dashboard / ".env").write_text("REACT_APP_API_PORT=5077\n", encoding="utf-8")
    node_version = tmp_path / ".nvmrc"
    node_version.write_text("24\n", encoding="utf-8")
    return dashboard, node_version


def _run_helper(
    script: str,
    *,
    dashboard: Path,
    node_version: Path,
    cache: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "HELPER": str(HELPER),
        "DASHBOARD": str(dashboard),
        "NODE_VERSION": str(node_version),
    }
    if cache is not None:
        env["CACHE"] = str(cache)
    return subprocess.run(
        ["bash", "-c", f'set -euo pipefail; source "$HELPER"; {script}'],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _fingerprint(dashboard: Path, node_version: Path) -> str:
    result = _run_helper(
        'pixeagle_dashboard_build_fingerprint "$DASHBOARD" "$NODE_VERSION"',
        dashboard=dashboard,
        node_version=node_version,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _complete_build(dashboard: Path) -> None:
    build = dashboard / "build"
    (build / "static" / "js").mkdir(parents=True)
    (build / "index.html").write_text("<script src='./static/js/main.js'></script>\n")
    (build / "static" / "js" / "main.js").write_text("console.log('ready');\n")
    (build / "asset-manifest.json").write_text(
        json.dumps(
            {
                "files": {
                    "main.js": "./static/js/main.js",
                    "index.html": "./index.html",
                },
                "entrypoints": ["static/js/main.js"],
            }
        ),
        encoding="utf-8",
    )


def test_fingerprint_changes_when_dashboard_environment_changes(tmp_path):
    dashboard, node_version = _dashboard_tree(tmp_path)
    initial = _fingerprint(dashboard, node_version)

    (dashboard / ".env").write_text("REACT_APP_API_PORT=5099\n", encoding="utf-8")

    assert _fingerprint(dashboard, node_version) != initial


def test_fingerprint_uses_source_content_not_mtime(tmp_path):
    dashboard, node_version = _dashboard_tree(tmp_path)
    source = dashboard / "src" / "index.js"
    initial = _fingerprint(dashboard, node_version)
    original_stat = source.stat()

    source.write_text("export default 2;\n", encoding="utf-8")
    os.utime(
        source,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    assert source.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert _fingerprint(dashboard, node_version) != initial


def test_fingerprint_changes_when_dependency_lock_changes(tmp_path):
    dashboard, node_version = _dashboard_tree(tmp_path)
    initial = _fingerprint(dashboard, node_version)

    (dashboard / "package-lock.json").write_text(
        '{"lockfileVersion":3,"packages":{"node_modules/example":{}}}\n',
        encoding="utf-8",
    )

    assert _fingerprint(dashboard, node_version) != initial


def test_cache_hit_requires_complete_referenced_build(tmp_path):
    dashboard, node_version = _dashboard_tree(tmp_path)
    _complete_build(dashboard)
    cache = dashboard / ".pixeagle_cache" / "build_hash"

    result = _run_helper(
        (
            'pixeagle_dashboard_publish_build_fingerprint '
            '"$DASHBOARD" "$NODE_VERSION" "$CACHE"; '
            'pixeagle_dashboard_build_cache_is_valid '
            '"$DASHBOARD" "$NODE_VERSION" "$CACHE"'
        ),
        dashboard=dashboard,
        node_version=node_version,
        cache=cache,
    )
    assert result.returncode == 0, result.stderr
    fingerprint = cache.read_text(encoding="utf-8").strip()
    assert len(fingerprint) == 64
    assert set(fingerprint) <= set("0123456789abcdef")

    (dashboard / "build" / "static" / "js" / "main.js").unlink()
    invalid = _run_helper(
        (
            'if pixeagle_dashboard_build_cache_is_valid '
            '"$DASHBOARD" "$NODE_VERSION" "$CACHE"; then exit 99; fi'
        ),
        dashboard=dashboard,
        node_version=node_version,
        cache=cache,
    )
    assert invalid.returncode == 0
    assert "missing referenced asset" in invalid.stderr


def test_incomplete_build_never_publishes_cache_marker(tmp_path):
    dashboard, node_version = _dashboard_tree(tmp_path)
    build = dashboard / "build"
    build.mkdir()
    (build / "index.html").write_text("<main></main>\n", encoding="utf-8")
    cache = dashboard / ".pixeagle_cache" / "build_hash"

    result = _run_helper(
        (
            'if pixeagle_dashboard_publish_build_fingerprint '
            '"$DASHBOARD" "$NODE_VERSION" "$CACHE"; then exit 99; fi'
        ),
        dashboard=dashboard,
        node_version=node_version,
        cache=cache,
    )

    assert result.returncode == 0
    assert "missing asset-manifest.json" in result.stderr
    assert not cache.exists()


def test_cache_marker_publication_rejects_symlinked_cache_directory(tmp_path):
    dashboard, node_version = _dashboard_tree(tmp_path)
    _complete_build(dashboard)
    external_cache = tmp_path / "external-cache"
    external_cache.mkdir()
    (dashboard / ".pixeagle_cache").symlink_to(external_cache, target_is_directory=True)
    cache = dashboard / ".pixeagle_cache" / "build_hash"

    result = _run_helper(
        (
            'if pixeagle_dashboard_publish_build_fingerprint '
            '"$DASHBOARD" "$NODE_VERSION" "$CACHE"; then exit 99; fi'
        ),
        dashboard=dashboard,
        node_version=node_version,
        cache=cache,
    )

    assert result.returncode == 0
    assert not (external_cache / "build_hash").exists()
