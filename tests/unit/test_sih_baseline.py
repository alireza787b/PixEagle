"""SIH build contracts use fake compiler/image outputs, never a simulator."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools import build_native_guidance, sih_baseline, sih_isolated_host


PIN = "a" * 64
BUILDER_ID = "sha256:" + "b" * 64
IMAGE_ID = "sha256:" + "c" * 64


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repository"
    extension = root / "native/px4"
    extension.mkdir(parents=True)
    patch = extension / "guidance.patch"
    patch.write_text("reviewed firmware patch")
    manifest = {"baseline_commit": "a" * 40,
                "patches": {patch.name: sih_baseline.digest(patch)},
                "files": {"controller.cpp": hashlib.sha256(b"reviewed controller").hexdigest()}}
    (extension / "extension.json").write_text(json.dumps(manifest))
    lock = {"reference_px4_commit": manifest["baseline_commit"], "sih_build": {
        "toolchain_image": "example/compiler:v1@sha256:" + PIN,
        "runtime_image": "example/runtime@sha256:" + PIN,
        "platform": "linux/amd64", "target": "px4_sitl_sih"}}
    (root / "native/dependencies.lock.json").write_text(json.dumps(lock))
    return root


def packaged_files(root):
    (root / "bin").mkdir(parents=True)
    header = bytearray(20)
    header[:6] = b"\x7fELF\x02\x01"
    header[18:20] = b"\x3e\x00"
    binary = root / "bin/px4"
    binary.write_bytes(header + b"compiled firmware")
    binary.chmod(0o755)
    (root / "bin/px4-alias.sh").write_text("alias commander=px4-commander\n")
    (root / "bin/px4-commander").symlink_to("px4")
    for name in ("init.d-posix/rcS", "init.d-posix/airframes/10040_sihsim_quadx"):
        path = root / "etc" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("matching runtime")


def build_manifest(repository, output):
    packaged_files(output / "packaged")
    firmware, spec = sih_baseline.authority(repository)
    artifacts = sih_baseline.artifact_manifest(output / "packaged")
    fingerprint = sih_baseline.recipe_fingerprint(firmware, spec)
    source = {"submodules": []}
    manifest = {"schema_version": 1, "kind": "pixeagle_sih_build", "firmware": firmware,
                "build": spec, "source": source, "artifacts": artifacts,
                "recipe_sha256": fingerprint, "image_id": IMAGE_ID}
    path = output / "sih-build-manifest.json"
    path.write_text(json.dumps(manifest))
    image = {"Id": IMAGE_ID, "Os": "linux", "Architecture": "amd64", "Config": {
        "Labels": sih_baseline.image_labels(fingerprint, artifacts, source)}}
    return path, manifest, image


def test_verified_manifest_binds_binary_romfs_aliases_patch_and_immutable_image(repository, tmp_path, monkeypatch):
    path, _, image = build_manifest(repository, tmp_path / "build")
    monkeypatch.setattr(sih_baseline, "command", lambda *args: json.dumps([image]))
    result = sih_baseline.validate_build_manifest(path, repository=repository)
    assert result["image_id"] == IMAGE_ID
    assert result["kind"] == "verified_source_build"
    assert result["firmware"]["commit"] == "a" * 40
    assert (path.parent / "packaged/bin/px4-commander").is_symlink()


@pytest.mark.parametrize("tamper", ["binary", "romfs", "alias", "image", "source", "patch", "recipe"])
def test_manifest_rejects_tampered_build_inputs(repository, tmp_path, monkeypatch, tamper):
    path, manifest, image = build_manifest(repository, tmp_path / "build")
    monkeypatch.setattr(sih_baseline, "command", lambda *args: json.dumps([image]))
    if tamper == "binary":
        with (path.parent / "packaged/bin/px4").open("ab") as stream:
            stream.write(b"changed")
    elif tamper == "romfs":
        (path.parent / "packaged/etc/init.d-posix/rcS").write_text("wrong startup")
    elif tamper == "alias":
        alias = path.parent / "packaged/bin/px4-commander"
        alias.unlink()
        alias.symlink_to("/bin/true")
    elif tamper == "image":
        image["Config"]["Labels"][f"{sih_baseline.LABEL}.artifacts"] = "wrong"
    elif tamper == "source":
        manifest["source"]["submodules"] = ["different source"]
    elif tamper == "patch":
        (repository / "native/px4/guidance.patch").write_text("unreviewed")
    else:
        manifest["recipe_sha256"] = "stale"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        sih_baseline.validate_build_manifest(path, repository=repository)


def test_source_verification_rejects_unlisted_changes_and_wrong_submodule_pin(repository, tmp_path, monkeypatch):
    source = tmp_path / "firmware"
    (source / ".git").mkdir(parents=True)
    outputs = {"diff": "controller.cpp", "ls-files": "", "submodule": " " + "d" * 40 + " module"}

    def git(*args):
        return next(value for key, value in outputs.items() if key in args)

    monkeypatch.setattr(sih_baseline, "command", git)
    verify = lambda *args: None
    sih_baseline.verify_source(source, repository, verify)
    outputs["diff"] = "controller.cpp\nEKF.cpp"
    with pytest.raises(ValueError, match="Unreviewed.*EKF"):
        sih_baseline.verify_source(source, repository, verify)
    outputs["diff"] = "controller.cpp"
    outputs["submodule"] = "+" + "e" * 40 + " module"
    with pytest.raises(ValueError, match="submodules"):
        sih_baseline.verify_source(source, repository, verify)


def test_source_verification_allows_only_manifested_deletions(repository, tmp_path, monkeypatch):
    manifest_path = repository / "native/px4/extension.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["deleted_files"] = ["obsolete_guard.hpp"]
    manifest_path.write_text(json.dumps(manifest))
    source = tmp_path / "firmware"
    (source / ".git").mkdir(parents=True)
    changed = ["controller.cpp\nobsolete_guard.hpp"]

    def git(*args):
        return changed[0] if "diff" in args else ""

    monkeypatch.setattr(sih_baseline, "command", git)
    sih_baseline.verify_source(source, repository, lambda *args: None)
    changed[0] += "\nunreviewed.cpp"
    with pytest.raises(ValueError, match="Unreviewed.*unreviewed.cpp"):
        sih_baseline.verify_source(source, repository, lambda *args: None)


def test_target_requires_its_modules_and_allows_absent_unused_platforms(repository, tmp_path, monkeypatch):
    lock_path = repository / "native/dependencies.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["sih_build"]["submodules"] = ["needed"]
    lock_path.write_text(json.dumps(lock))
    source = tmp_path / "source"
    (source / ".git").mkdir(parents=True)
    status = [" " + "d" * 40 + " needed\n-" + "e" * 40 + " unused"]

    def git(*args):
        return status[0] if "submodule" in args else ""

    monkeypatch.setattr(sih_baseline, "command", git)
    result = sih_baseline.verify_source(source, repository, lambda *args: None)
    assert len(result["submodules"]) == 1
    status[0] = "-" + "d" * 40 + " needed"
    with pytest.raises(ValueError, match="submodules"):
        sih_baseline.verify_source(source, repository, lambda *args: None)


def test_microcdr_cache_checks_both_commit_and_upstream_tag(tmp_path, monkeypatch):
    pin = {"commit": "d" * 40, "repository": "https://example/Micro-CDR.git", "tag": "v2.0.1"}
    cached = tmp_path / ("Micro-CDR-" + pin["commit"])
    (cached / ".git").mkdir(parents=True)
    tag = [pin["commit"]]

    def git(*args):
        if "status" in args:
            return ""
        return tag[0] if args[-1].endswith("^{commit}") else pin["commit"]

    monkeypatch.setattr(sih_baseline, "command", git)
    assert sih_baseline.prepare_microcdr({"microcdr": pin}, tmp_path) == cached
    tag[0] = "e" * 40
    with pytest.raises(ValueError, match="Micro-CDR"):
        sih_baseline.prepare_microcdr({"microcdr": pin}, tmp_path)


def test_prepare_excludes_cached_executable_and_does_not_call_docker(repository, tmp_path, monkeypatch):
    source = tmp_path / "firmware"
    (source / "build/px4_sitl_sih/bin").mkdir(parents=True)
    (source / "build/px4_sitl_sih/bin/px4").write_text("unverified cached binary")
    (source / "controller.cpp").write_text("reviewed controller")
    monkeypatch.setattr(sih_baseline, "verify_source", lambda *args: {"submodules": []})
    monkeypatch.setattr(sih_baseline, "command", lambda *args: pytest.fail("prepare must not call Docker"))
    output = tmp_path / "prepared"
    path = sih_baseline.build_sih(source, output, prepare_only=True, verify_extension=lambda *args: None,
                                  repository=repository)
    assert path.name == "build-plan.json"
    assert not (output / "context/source/build").exists()
    assert not (output / "sih-build-manifest.json").exists()
    assert "DONT_RUN=1 make px4_sitl_sih" in (output / "context/Dockerfile.firmware").read_text()


def test_mock_compilation_packages_matching_outputs_without_starting_a_container(repository, tmp_path, monkeypatch):
    source = tmp_path / "firmware"
    source.mkdir()
    monkeypatch.setattr(sih_baseline, "verify_source", lambda *args: {"submodules": []})
    commands = []
    output = tmp_path / "build"

    def docker(*args):
        commands.append(args)
        assert args[:2] not in [("docker", "run"), ("docker", "start")]
        if args[:3] == ("docker", "image", "inspect"):
            ref = args[3]
            image = {"Id": IMAGE_ID, "Os": "linux", "Architecture": "amd64", "RepoDigests": [
                "example/compiler@sha256:" + PIN, "example/runtime@sha256:" + PIN]}
            if ref == IMAGE_ID:
                firmware, spec = sih_baseline.authority(repository)
                artifacts = sih_baseline.artifact_manifest(output / "packaged")
                image["Config"] = {"Labels": sih_baseline.image_labels(
                    sih_baseline.recipe_fingerprint(firmware, spec), artifacts, {"submodules": []})}
            return json.dumps([image])
        if args[:2] == ("docker", "build"):
            iid = Path(args[args.index("--iidfile") + 1])
            iid.write_text(BUILDER_ID if "--file" in args else IMAGE_ID)
        elif args[:2] == ("docker", "create"):
            return "stopped-build-artifacts"
        elif args[:2] == ("docker", "cp") and args[-1].endswith("/bin"):
            packaged_files(output / "packaged")
        return ""

    monkeypatch.setattr(sih_baseline, "command", docker)
    path = sih_baseline.build_sih(source, output, prepare_only=False, verify_extension=lambda *args: None,
                                  repository=repository)
    assert json.loads(path.read_text())["image_id"] == IMAGE_ID
    assert sum(args[:2] == ("docker", "build") for args in commands) == 2
    assert (output / "packaged/bin/px4-commander").readlink() == Path("px4")


def test_sih_cli_dispatches_before_ros_dependency_preparation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(build_native_guidance.sys, "argv", ["build_native_guidance.py", "--target", "sih",
                        "--prepare-only", "--px4-source", str(tmp_path), "--output-dir", str(tmp_path / "out")])
    monkeypatch.setattr(build_native_guidance, "prepare_sources", lambda *args: pytest.fail("ROS preparation"))
    monkeypatch.setattr(sih_baseline, "build_sih", lambda *args, **kwargs: calls.append((args, kwargs)))
    build_native_guidance.main()
    assert calls[0][1]["prepare_only"] is True


def test_missing_compiler_dependency_retains_failure_without_a_selectable_manifest(repository, tmp_path, monkeypatch):
    source = tmp_path / "firmware"
    source.mkdir()
    monkeypatch.setattr(sih_baseline, "verify_source", lambda *args: {"submodules": []})

    def docker(*args):
        if args[:3] == ("docker", "image", "inspect"):
            return json.dumps([{"Id": IMAGE_ID, "Os": "linux", "Architecture": "amd64",
                                "RepoDigests": [args[-1]]}])
        raise subprocess.CalledProcessError(1, args, output="missing pinned compiler dependency")

    monkeypatch.setattr(sih_baseline, "command", docker)
    output = tmp_path / "failed-build"
    with pytest.raises(subprocess.CalledProcessError):
        sih_baseline.build_sih(source, output, prepare_only=False, verify_extension=lambda *args: None,
                              repository=repository)
    assert "missing pinned" in (output / "firmware-build.log").read_text()
    assert not (output / "sih-build-manifest.json").exists()


def test_host_refuses_an_explicit_invalid_manifest_before_creating_evidence(tmp_path, monkeypatch):
    def invalid(path):
        raise ValueError("invalid SIH build")

    monkeypatch.setattr(sih_baseline, "validate_build_manifest", invalid)
    args = argparse.Namespace(execute=True, backend_repo=tmp_path, output=tmp_path / "evidence",
                              sih_build_manifest=tmp_path / "wrong.json")
    with pytest.raises(ValueError, match="invalid SIH"):
        sih_isolated_host.host(args, driver_path=tmp_path / "driver.py")
    assert not args.output.exists()


def test_host_launches_explicit_verified_immutable_id_and_records_selection(tmp_path, monkeypatch):
    repo = tmp_path / "source"
    for name in ("src/classes/app_controller.py", "tools/sitl_gimbal_geometry_fixture.py"):
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n")
    (repo / "configs").mkdir()
    (repo / "configs/config_default.yaml").write_bytes(
        (sih_baseline.ROOT / "configs/config_default.yaml").read_bytes())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("mavsdk_server_bin", "mavlink2rest"):
        (bin_dir / name).write_text("sidecar fixture")
    selected = {"kind": "verified_source_build", "image_id": IMAGE_ID, "manifest_sha256": PIN}
    monkeypatch.setattr(sih_baseline, "validate_build_manifest", lambda path: selected)

    def host_command(*args):
        if args[0] == "git":
            return "configs/config_default.yaml" if "ls-files" in args else ""
        if args[0] == sys.executable:
            return "[]"
        if args[:3] == ("docker", "image", "inspect"):
            return json.dumps([{"Id": IMAGE_ID}])
        if args[:2] == ("docker", "run"):
            assert args[-1] == IMAGE_ID
            assert args[args.index("--network") + 1] == "none"
            raise RuntimeError("fixture stops before launching any process")
        raise AssertionError(args)

    monkeypatch.setattr(sih_isolated_host, "command", host_command)
    monkeypatch.setattr(sih_isolated_host.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    args = argparse.Namespace(execute=True, backend_repo=repo, output=tmp_path / "evidence",
                              sih_build_manifest=tmp_path / "verified.json", python=Path(sys.executable),
                              bin_dir=bin_dir, follower="mc_velocity_position", mount="HORIZONTAL")
    with pytest.raises(RuntimeError, match="fixture stops"):
        sih_isolated_host.host(args, driver_path=repo / "src/classes/app_controller.py")
    retained = json.loads((args.output / "manifest.json").read_text())
    assert retained["sih_baseline"] == selected
    assert retained["px4_image"] == IMAGE_ID
