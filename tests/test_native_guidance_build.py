import hashlib
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace

import pytest

from tools.build_native_guidance import apply_message_overlay, apply_sdk_extension, prepare_sources, verify_extension


def test_native_build_uses_pinned_verified_archive_without_network(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    name = "example"
    commit = "a" * 40
    tree = tmp_path / f"{name}-{commit}"
    tree.mkdir()
    (tree / "version.txt").write_text(commit)
    archive = cache / f"{name}-{commit}.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(tree, arcname=tree.name)
    lock = {"sources": [{"repository": f"owner/{name}", "commit": commit,
                          "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}]}
    destination = tmp_path / "sources"
    prepare_sources(lock, cache, destination)
    assert (destination / tree.name / "version.txt").read_text() == commit
    archive.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum mismatch"):
        prepare_sources(lock, cache, tmp_path / "corrupt")
    assert not (tmp_path / "corrupt" / tree.name).exists()


def test_message_extension_only_overlays_the_pinned_source(tmp_path):
    messages = tmp_path / "dependencies" / "px4_msgs-test" / "msg"
    messages.mkdir(parents=True)
    (messages / "VehicleStatus.msg").write_text("native baseline")
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "FixedWingGuidanceStatus.msg").write_text("reviewed extension")
    lock = {"sources": [{"repository": "PX4/px4_msgs", "commit": "test"}]}
    apply_message_overlay(tmp_path / "dependencies", lock, overlay)
    assert (messages / "VehicleStatus.msg").read_text() == "native baseline"
    assert (messages / "FixedWingGuidanceStatus.msg").read_text() == "reviewed extension"
    with pytest.raises(ValueError, match="missing"):
        apply_message_overlay(tmp_path / "missing", lock, overlay)


@pytest.fixture
def sdk_overlay(tmp_path):
    dependencies, extension = tmp_path / "dependencies", tmp_path / "extension"
    sdk = dependencies / "px4-ros2-interface-lib-pinned"
    sdk.mkdir(parents=True)
    extension.mkdir()
    original, patched = b"baseline\n", b"accessor\n"
    (sdk / "header.hpp").write_bytes(original)
    patch = extension / "accessor.patch"
    patch.write_text("--- a/header.hpp\n+++ b/header.hpp\n@@ -1 +1 @@\n-baseline\n+accessor\n")
    manifest = {"repository": "Auterion/px4-ros2-interface-lib", "baseline_commit": "pinned",
                "patches": {patch.name: hashlib.sha256(patch.read_bytes()).hexdigest()},
                "original_files": {"header.hpp": hashlib.sha256(original).hexdigest()},
                "files": {"header.hpp": hashlib.sha256(patched).hexdigest()}}
    manifest_path = extension / "extension.json"
    manifest_path.write_text(json.dumps(manifest))
    lock = {"sources": [{"repository": manifest["repository"], "commit": "pinned",
                          "extension_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest()}]}
    return dependencies, extension, lock


def test_sdk_overlay_applies_only_to_the_locked_baseline(sdk_overlay):
    dependencies, extension, lock = sdk_overlay
    apply_sdk_extension(dependencies, lock, extension)
    header = dependencies / "px4-ros2-interface-lib-pinned/header.hpp"
    assert header.read_bytes() == b"accessor\n"
    with pytest.raises(ValueError, match="header.hpp"):
        apply_sdk_extension(dependencies, lock, extension)


@pytest.mark.parametrize("tamper", ["manifest", "missing_manifest", "patch", "missing_patch", "baseline", "result"])
def test_sdk_overlay_rejects_unreviewed_inputs_and_output(sdk_overlay, tamper):
    dependencies, extension, lock = sdk_overlay
    manifest_path = extension / "extension.json"
    if tamper == "manifest":
        manifest_path.write_text("{}")
    elif tamper == "missing_manifest":
        manifest_path.unlink()
    elif tamper == "patch":
        (extension / "accessor.patch").write_text("unreviewed patch")
    elif tamper == "missing_patch":
        (extension / "accessor.patch").unlink()
    elif tamper == "baseline":
        (dependencies / "px4-ros2-interface-lib-pinned/header.hpp").write_text("other SDK")
    else:
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["header.hpp"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest))
        lock["sources"][0]["extension_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="checksum mismatch"):
        apply_sdk_extension(dependencies, lock, extension)


def test_sdk_overlay_rejects_a_different_locked_commit(sdk_overlay):
    dependencies, extension, lock = sdk_overlay
    lock["sources"][0]["commit"] = "other"
    with pytest.raises(ValueError, match="baseline mismatch"):
        apply_sdk_extension(dependencies, lock, extension)


def test_prepare_only_builds_from_sdk_overlay_and_records_its_pin(sdk_overlay, tmp_path, monkeypatch):
    import shutil
    from tools import build_native_guidance as builder

    dependencies, extension, lock = sdk_overlay
    root, output = tmp_path / "repo", tmp_path / "output"
    native = root / "native"
    native.mkdir(parents=True)
    shutil.copytree(extension, native / "ros2_interface")
    (native / "dependencies.lock.json").write_text(json.dumps(lock))
    (native / "px4/messages").mkdir(parents=True)
    (native / "px4_guidance").mkdir()
    (native / "Dockerfile.tests").write_text("FROM unused\n")

    def prepare(_lock, _cache, destination):
        shutil.copytree(dependencies, destination)

    # The unrelated message overlay is independently covered above.
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "prepare_sources", prepare)
    monkeypatch.setattr(builder, "apply_message_overlay", lambda *args: None)
    monkeypatch.setattr("sys.argv", ["build_native_guidance.py", "--prepare-only", "--output-dir", str(output)])
    builder.main()
    assert (output / "build-context/dependencies/px4-ros2-interface-lib-pinned/header.hpp").read_bytes() == b"accessor\n"
    assert (output / "sdk-extension.json").read_bytes() == (extension / "extension.json").read_bytes()
    assert json.loads((output / "dependencies.lock.json").read_text()) == lock


def test_checked_in_sdk_overlay_is_pinned_by_the_existing_dependency_lock():
    root = Path(__file__).resolve().parents[1]
    extension = root / "native/ros2_interface"
    manifest_path = extension / "extension.json"
    lock = json.loads((root / "native/dependencies.lock.json").read_text())
    source = next(item for item in lock["sources"] if item["repository"] == "Auterion/px4-ros2-interface-lib")
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == source["extension_manifest_sha256"]
    manifest = json.loads(manifest_path.read_text())
    assert manifest["baseline_commit"] == source["commit"]
    assert manifest["repository"] == source["repository"]
    assert manifest["original_files"].keys() == manifest["files"].keys()
    for name, checksum in manifest["patches"].items():
        assert hashlib.sha256((extension / name).read_bytes()).hexdigest() == checksum


def test_owned_mode_overlay_preserves_standard_command_and_status_definitions(tmp_path):
    messages = tmp_path / "dependencies" / "px4_msgs-pinned" / "msg"
    messages.mkdir(parents=True)
    standard = {"VehicleCommand.msg": b"standard command v1\n", "VehicleStatus.msg": b"standard status v5\n"}
    for name, content in standard.items():
        (messages / name).write_bytes(content)
    overlay = Path(__file__).resolve().parents[1] / "native/px4/messages"
    assert {path.name for path in overlay.glob("*.msg")} == {
        "FixedWingGuidanceStatus.msg", "OwnedModeRequest.msg", "OwnedModeStatus.msg",
    }
    apply_message_overlay(tmp_path / "dependencies", {
        "sources": [{"repository": "PX4/px4_msgs", "commit": "pinned"}],
    }, overlay)
    for name, content in standard.items():
        assert (messages / name).read_bytes() == content
    for source in overlay.glob("*.msg"):
        assert (messages / source.name).read_bytes() == source.read_bytes()


def test_extension_checks_firmware_baseline_patch_and_applied_sources(tmp_path, monkeypatch):
    source, extension = tmp_path / "firmware", tmp_path / "extension"
    source.mkdir()
    extension.mkdir()
    (source / "controller.cpp").write_text("reviewed controller")
    (extension / "guidance.patch").write_text("reviewed patch")
    manifest = {"baseline_commit": "pinned", "patches": {
        "guidance.patch": hashlib.sha256((extension / "guidance.patch").read_bytes()).hexdigest(),
    }, "files": {"controller.cpp": hashlib.sha256((source / "controller.cpp").read_bytes()).hexdigest()}}
    (extension / "extension.json").write_text(json.dumps(manifest))
    monkeypatch.setattr("tools.build_native_guidance.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout="pinned\n"))
    verify_extension(source, extension)
    (source / "controller.cpp").write_text("different controller")
    with pytest.raises(ValueError, match="controller.cpp"):
        verify_extension(source, extension)
    (source / "controller.cpp").write_text("reviewed controller")
    (extension / "guidance.patch").write_text("unreviewed patch")
    with pytest.raises(ValueError, match="guidance.patch"):
        verify_extension(source, extension)
    monkeypatch.setattr("tools.build_native_guidance.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout="wrong\n"))
    with pytest.raises(ValueError, match="baseline"):
        verify_extension(source, extension)


@pytest.mark.parametrize("retained", ["file", "directory", "dangling_symlink"])
def test_extension_requires_removed_sources_to_be_absent(tmp_path, monkeypatch, retained):
    source, extension = tmp_path / "firmware", tmp_path / "extension"
    source.mkdir()
    extension.mkdir()
    removed = source / "obsolete_guard.hpp"
    manifest = {"baseline_commit": "pinned", "patches": {}, "files": {},
                "deleted_files": [removed.name]}
    (extension / "extension.json").write_text(json.dumps(manifest))
    monkeypatch.setattr("tools.build_native_guidance.subprocess.run",
                        lambda *args, **kwargs: SimpleNamespace(stdout="pinned\n"))
    verify_extension(source, extension)
    if retained == "file":
        removed.write_text("obsolete implementation")
    elif retained == "directory":
        removed.mkdir()
    else:
        removed.symlink_to(source / "missing")
    with pytest.raises(ValueError, match="Removed.*obsolete_guard"):
        verify_extension(source, extension)
