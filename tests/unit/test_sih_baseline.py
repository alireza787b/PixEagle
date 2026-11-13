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
    (tmp_path / "wrong.json").write_text(json.dumps({"kind": "pixeagle_sih_build"}))
    args = argparse.Namespace(execute=True, backend_repo=tmp_path, output=tmp_path / "evidence",
                              simulation_build_manifest=tmp_path / "wrong.json")
    with pytest.raises(ValueError, match="invalid SIH"):
        sih_isolated_host.host(args, driver_path=tmp_path / "driver.py")
    assert not args.output.exists()


@pytest.mark.parametrize("simulator", ["sih", "gazebo"])
def test_host_launches_explicit_verified_immutable_id_and_records_selection(tmp_path, monkeypatch, simulator):
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
    spec = json.loads((sih_baseline.ROOT / "native/dependencies.lock.json").read_text())[simulator + "_build"]
    (tmp_path / "verified.json").write_text(json.dumps({"kind": f"pixeagle_{simulator}_build", "build": spec}))
    selected = {"kind": "verified_source_build" if simulator == "sih" else "verified_gazebo_source_build",
                "image_id": IMAGE_ID, "manifest_sha256": sih_baseline.digest(tmp_path / "verified.json")}
    monkeypatch.setattr(sih_baseline, "validate_build_manifest", lambda path, **kwargs: selected)

    def host_command(*args):
        if args[0] == "git":
            return "configs/config_default.yaml" if "ls-files" in args else ""
        if args[0] == sys.executable:
            return "[]"
        if args[:3] == ("docker", "image", "inspect"):
            return json.dumps([{"Id": IMAGE_ID}])
        if args[:2] == ("docker", "run"):
            assert IMAGE_ID in args
            assert args[args.index("--network") + 1] == "none"
            assert not {"--privileged", "--device", "--publish", "-p"} & set(args)
            if simulator == "gazebo":
                assert args[args.index(IMAGE_ID) + 1:] == ("-i", "0", "-w", "/work/rootfs", "/opt/px4/etc")
                assert "PX4_SIM_MODEL=gz_quadtailsitter" in args and "PX4_GZ_WORLD=default" in args
                assert "--user" in args and "GZ_IP=127.0.0.1" in args
                assert any(arg.startswith("GZ_PARTITION=") for arg in args)
            else:
                assert args[args.index(IMAGE_ID) + 1:] == ("-i", "0", "-w", "/work/rootfs", "/opt/px4/etc")
                assert "PX4_SIM_MODEL=sihsim_quadx" in args and "--user" in args
            raise RuntimeError("fixture stops before launching any process")
        raise AssertionError(args)

    monkeypatch.setattr(sih_isolated_host, "command", host_command)
    monkeypatch.setattr(sih_isolated_host.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    args = argparse.Namespace(execute=True, backend_repo=repo, output=tmp_path / "evidence",
                              simulation_build_manifest=tmp_path / "verified.json", python=Path(sys.executable),
                              bin_dir=bin_dir, follower="mc_velocity_position", mount="HORIZONTAL")
    with pytest.raises(RuntimeError, match="fixture stops"):
        sih_isolated_host.host(args, driver_path=repo / "src/classes/app_controller.py")
    retained = json.loads((args.output / "manifest.json").read_text())
    assert retained["sih_baseline"] == selected
    assert retained["px4_image"] == IMAGE_ID
    assert retained["simulator"] == simulator


@pytest.fixture
def gazebo_repository(repository):
    lock_path = repository / "native/dependencies.lock.json"
    lock = json.loads(lock_path.read_text())
    spec = json.loads((sih_baseline.ROOT / "native/dependencies.lock.json").read_text())["gazebo_build"]
    spec.update(toolchain_image=lock["sih_build"]["toolchain_image"],
                runtime_image=lock["sih_build"]["runtime_image"])
    spec.pop("microcdr", None)
    lock["gazebo_build"] = spec
    lock_path.write_text(json.dumps(lock))
    return repository


def gazebo_resources(root):
    for relative in ("models/quadtailsitter/model.sdf", "models/airspeed/model.sdf", "worlds/default.sdf"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"pinned {relative}\n")
    (root / "server.config").write_text("pinned server configuration\n")
    return {"models": sih_baseline.tree_manifest(root / "models"),
            "worlds": sih_baseline.tree_manifest(root / "worlds"),
            "server_config_sha256": sih_baseline.digest(root / "server.config")}


@pytest.mark.parametrize("change", ["target", "distribution", "model", "world", "airframe_id", "missing_pin",
                                    "bad_pin", "missing_submodule", "toolchain_image", "runtime_image"])
def test_gazebo_recipe_rejects_unpinned_or_incompatible_inputs_before_preparation(
        gazebo_repository, tmp_path, monkeypatch, change):
    path = gazebo_repository / "native/dependencies.lock.json"
    lock = json.loads(path.read_text())
    spec = lock["gazebo_build"]
    if change == "missing_pin":
        del spec["submodule_pins"]["Tools/simulation/gz"]
    elif change == "bad_pin":
        spec["submodule_pins"]["Tools/simulation/gz"] = "main"
    elif change == "missing_submodule":
        spec["submodules"].remove("Tools/simulation/gz")
    else:
        spec[change] = None if change.endswith("_image") else "unreviewed"
    path.write_text(json.dumps(lock))
    monkeypatch.setattr(sih_baseline, "command", lambda *args: pytest.fail("must reject before external commands"))
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        sih_baseline.build_simulator(tmp_path / "source", output, prepare_only=True,
                                    verify_extension=lambda *args: None, repository=gazebo_repository, simulator="gazebo")
    assert not output.exists()


def test_unknown_simulator_cannot_select_an_arbitrary_make_target(repository):
    with pytest.raises(ValueError, match="Unsupported simulator"):
        sih_baseline.authority(repository, simulator="gz_quadtailsitter")


def test_gazebo_source_requires_actual_locked_resource_commits(gazebo_repository, tmp_path, monkeypatch):
    source = tmp_path / "source"
    (source / ".git").mkdir(parents=True)
    resource_root = source / "Tools/simulation/gz"
    expected = gazebo_resources(resource_root)
    server = source / sih_baseline.GAZEBO_SERVER_CONFIG
    server.parent.mkdir(parents=True)
    server.write_bytes((resource_root / "server.config").read_bytes())
    _, spec = sih_baseline.authority(gazebo_repository, simulator="gazebo")
    status = ["\n".join(" " + spec["submodule_pins"].get(name, "b" * 40) + " " + name
                        for name in spec["submodules"])]
    monkeypatch.setattr(sih_baseline, "command", lambda *args: status[0] if "submodule" in args else "")
    verify = lambda *args: None
    result = sih_baseline.verify_source(source, gazebo_repository, verify, simulator="gazebo")
    assert result["gazebo_resources"] == expected
    status[0] = status[0].replace(spec["submodule_pins"]["Tools/simulation/gz"], "d" * 40)
    with pytest.raises(ValueError, match="locked commit"):
        sih_baseline.verify_source(source, gazebo_repository, verify, simulator="gazebo")


def test_gazebo_prepare_only_has_no_launch_target_or_docker_command(gazebo_repository, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(sih_baseline, "verify_source", lambda *args, **kwargs: {"submodules": []})
    monkeypatch.setattr(sih_baseline, "command", lambda *args: pytest.fail("prepare must not call Docker"))
    output = tmp_path / "prepared"
    path = sih_baseline.build_simulator(source, output, prepare_only=True, verify_extension=lambda *args: None,
                                      repository=gazebo_repository, simulator="gazebo")
    plan = json.loads(path.read_text())
    assert plan["command"][:3] == ["make", "px4_sitl_default", "-j2"]
    assert "gz_quadtailsitter" not in plan["command"]
    recipe = (output / "context/Dockerfile.firmware").read_text()
    assert "RUN DONT_RUN=1 GZ_DISTRO=harmonic make px4_sitl_default -j2" in recipe
    assert "gz sim" not in recipe
    assert not (output / "gazebo-build-manifest.json").exists()


def test_gazebo_mock_build_binds_resources_and_is_not_a_sih_manifest(gazebo_repository, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    staged = tmp_path / "resources"
    resources = gazebo_resources(staged)
    provenance = {"submodules": [], "gazebo_resources": resources}
    monkeypatch.setattr(sih_baseline, "verify_source", lambda *args, **kwargs: provenance)
    commands = []
    output = tmp_path / "build"

    def docker(*args):
        import shutil

        commands.append(args)
        assert args[:2] not in [("docker", "run"), ("docker", "start"), ("docker", "exec")]
        if args[:3] == ("docker", "image", "inspect"):
            image = {"Id": IMAGE_ID, "Os": "linux", "Architecture": "amd64", "RepoDigests": [
                "example/compiler@sha256:" + PIN, "example/runtime@sha256:" + PIN]}
            if args[3] == IMAGE_ID:
                firmware, spec = sih_baseline.authority(gazebo_repository, simulator="gazebo")
                artifacts = sih_baseline.artifact_manifest(output / "packaged", simulator="gazebo")
                image["Config"] = {"Labels": sih_baseline.image_labels(
                    sih_baseline.recipe_fingerprint(firmware, spec), artifacts, provenance, simulator="gazebo")}
            return json.dumps([image])
        if args[:2] == ("docker", "build"):
            assert "--network=none" in args and "--pull=false" in args
            Path(args[args.index("--iidfile") + 1]).write_text(BUILDER_ID if "--file" in args else IMAGE_ID)
        elif args[:2] == ("docker", "create"):
            assert args[args.index("--entrypoint") + 1] == "/bin/true"
            return "never-started-artifacts"
        elif args[:2] == ("docker", "cp"):
            destination = Path(args[-1])
            if destination.name == "bin":
                packaged_files(output / "packaged")
                (output / "packaged/etc/init.d-posix/airframes/4018_gz_quadtailsitter").write_text("4018")
            elif destination.name in ("models", "worlds"):
                shutil.copytree(staged / destination.name, destination)
            elif destination.name == "server.config":
                shutil.copyfile(staged / destination.name, destination)
            elif destination.name == "plugins":
                destination.mkdir()
                for library in ("libOpticalFlowSystem.so", "libOpticalFlow.so", "libAirSpeedPlugin.so", "libGstCameraSystem.so"):
                    (destination / library).write_bytes(b"compiled plugin")
        return ""

    monkeypatch.setattr(sih_baseline, "command", docker)
    path = sih_baseline.build_simulator(source, output, prepare_only=False, verify_extension=lambda *args: None,
                                      repository=gazebo_repository, simulator="gazebo")
    manifest = json.loads(path.read_text())
    assert path.name == "gazebo-build-manifest.json"
    assert manifest["kind"] == "pixeagle_gazebo_build"
    assert not manifest["hardware_qualified"] and not manifest["response_qualified"]
    assert manifest["source"]["gazebo_resources"] == resources
    assert "plugins/libAirSpeedPlugin.so" in manifest["artifacts"]["gazebo"]
    assert sum(args[:2] == ("docker", "build") for args in commands) == 2
    runtime = (output / "packaged/Dockerfile").read_text()
    assert "org.pixeagle.gazebo.recipe" in runtime and "org.pixeagle.sih.recipe" not in runtime
    assert "GZ_SIM_SERVER_CONFIG_PATH=/opt/px4/gazebo/server.config" in runtime
    assert sih_baseline.validate_build_manifest(path, repository=gazebo_repository, simulator="gazebo")[
        "kind"] == "verified_gazebo_source_build"
    with pytest.raises(ValueError, match="reviewed build recipe"):
        sih_baseline.validate_build_manifest(path, repository=gazebo_repository)
    (output / "packaged/gazebo/models/quadtailsitter/model.sdf").write_text("different physics")
    with pytest.raises(ValueError, match="differs from the build manifest"):
        sih_baseline.validate_build_manifest(path, repository=gazebo_repository, simulator="gazebo")


def test_gazebo_rejects_packaged_resource_substitution_even_with_updated_artifact_hash(tmp_path):
    expected = gazebo_resources(tmp_path / "source")
    gazebo_resources(tmp_path / "package")
    (tmp_path / "package/worlds/default.sdf").write_text("different gravity")
    with pytest.raises(ValueError, match="worlds differ"):
        sih_baseline.verify_packaged_resources({"gazebo": sih_baseline.tree_manifest(tmp_path / "package")},
                                              {"gazebo_resources": expected})


def test_gazebo_cli_dispatches_build_only_before_ros_preparation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(build_native_guidance.sys, "argv", ["build_native_guidance.py", "--target", "gazebo",
                        "--prepare-only", "--px4-source", str(tmp_path), "--output-dir", str(tmp_path / "out")])
    monkeypatch.setattr(build_native_guidance, "prepare_sources", lambda *args: pytest.fail("ROS preparation"))
    monkeypatch.setattr(sih_baseline, "build_simulator", lambda *args, **kwargs: calls.append(kwargs))
    build_native_guidance.main()
    assert calls == [{"prepare_only": True, "verify_extension": build_native_guidance.verify_extension,
                      "cache": Path.home() / ".cache/pixeagle-native-guidance", "simulator": "gazebo"}]


@pytest.mark.parametrize("missing", ["models/quadtailsitter/model.sdf", "models/airspeed/model.sdf",
                                     "worlds/default.sdf", "server.config", "plugins/libOpticalFlowSystem.so",
                                     "plugins/libOpticalFlow.so", "plugins/libAirSpeedPlugin.so", "plugins/libGstCameraSystem.so"])
def test_gazebo_artifact_manifest_rejects_missing_runtime_resources(tmp_path, missing):
    packaged_files(tmp_path)
    (tmp_path / "etc/init.d-posix/airframes/4018_gz_quadtailsitter").write_text("4018")
    gazebo_resources(tmp_path / "gazebo")
    (tmp_path / "gazebo/plugins").mkdir()
    for name in ("libOpticalFlowSystem.so", "libOpticalFlow.so", "libAirSpeedPlugin.so", "libGstCameraSystem.so"):
        (tmp_path / "gazebo/plugins" / name).write_bytes(b"plugin")
    (tmp_path / "gazebo" / missing).unlink()
    with pytest.raises(ValueError, match="Missing Gazebo runtime resource"):
        sih_baseline.artifact_manifest(tmp_path, simulator="gazebo")


def test_sih_generated_dockerfiles_keep_the_existing_commands_and_runtime_contract(repository, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(sih_baseline, "verify_source", lambda *args: {"submodules": []})
    output = tmp_path / "prepared"
    sih_baseline.build_sih(source, output, prepare_only=True, verify_extension=lambda *args: None,
                           repository=repository)
    spec = sih_baseline.authority(repository)[1]
    assert (output / "context/Dockerfile.firmware").read_text() == (
        f"FROM {spec['toolchain_image']}\n"
        "COPY source/ /work/px4-simulation-source/\n"
        "WORKDIR /work/px4-simulation-source\n"
        "RUN cmake --version && ninja --version && c++ --version && python3 --version\n"
        "RUN DONT_RUN=1 make px4_sitl_sih -j2\n"
    )
    assert json.loads((output / "build-plan.json").read_text())["qualification"] == (
        "build inputs only; no SIH response qualification")
