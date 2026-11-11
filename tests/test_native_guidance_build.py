import hashlib
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace

import pytest

from tools.build_native_guidance import apply_message_overlay, prepare_sources, verify_extension


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
