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
    (root / "tools").mkdir(parents=True)
    (root / "tools/sih_baseline.py").write_bytes(Path(sih_baseline.__file__).read_bytes())
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


def build_manifest(repository, output, *, firmware_policy="experimental"):
    packaged_files(output / "packaged")
    firmware, spec = sih_baseline.authority(repository, firmware_policy=firmware_policy)
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


@pytest.fixture
def stock_repository(repository):
    path = repository / "native/dependencies.lock.json"
    lock = json.loads(path.read_text())
    lock["stock_px4"] = {
        "commit": "b" * 40,
        "version": {"describe": "v1.18.0-beta1-1-gbbbbbbbb", "tag": "v1.18.0-beta1",
                    "tag_object": "c" * 40, "tag_commit": "d" * 40},
        "additional_sih_submodules": ["src/lib/cdrstream/cyclonedds"],
    }
    path.write_text(json.dumps(lock))
    return repository


def test_stock_authority_has_no_extension_dependency(stock_repository):
    (stock_repository / "native/px4/extension.json").unlink()
    firmware, spec = sih_baseline.authority(stock_repository, firmware_policy="stock")
    assert firmware["policy"] == "stock" and firmware["patches"] == {}
    assert firmware["commit"] == "b" * 40
    assert "extension_sha256" not in firmware
    assert spec["submodules"] == ["src/lib/cdrstream/cyclonedds"]


@pytest.mark.parametrize("extra", [["../other"], ["/tmp/other"], [True], [["nested"]], ["a", "a"]])
def test_stock_authority_rejects_invalid_dependency_paths(stock_repository, extra):
    path = stock_repository / "native/dependencies.lock.json"
    lock = json.loads(path.read_text())
    lock["stock_px4"]["additional_sih_submodules"] = extra
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError, match="submodule"):
        sih_baseline.authority(stock_repository, firmware_policy="stock")


def test_stock_policy_cannot_select_gazebo_or_unknown_firmware(stock_repository):
    with pytest.raises(ValueError, match="SIH only"):
        sih_baseline.authority(stock_repository, simulator="gazebo", firmware_policy="stock")
    with pytest.raises(ValueError, match="Unknown.*policy"):
        sih_baseline.authority(stock_repository, firmware_policy="guess")


def test_stock_manifest_cannot_be_relabelled_as_experimental(stock_repository, tmp_path, monkeypatch):
    path, manifest, image = build_manifest(stock_repository, tmp_path / "stock-build", firmware_policy="stock")
    monkeypatch.setattr(sih_baseline, "command", lambda *args: json.dumps([image]))
    assert sih_baseline.validate_build_manifest(path, repository=stock_repository)["firmware"]["policy"] == "stock"
    manifest["firmware"].pop("policy")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="reviewed build recipe"):
        sih_baseline.validate_build_manifest(path, repository=stock_repository)


@pytest.mark.parametrize("tamper", ["commit", "tracked", "untracked", "submodule"])
def test_stock_source_refuses_patches_and_wrong_revisions(stock_repository, tmp_path, monkeypatch, tamper):
    source = tmp_path / "stock"
    (source / ".git").mkdir(parents=True)
    state = {"head": "b" * 40, "tracked": "", "untracked": "", "submodule": " " + "e" * 40
             + " src/lib/cdrstream/cyclonedds"}

    def git(*args):
        if "rev-parse" in args:
            return state["head"]
        if "diff" in args:
            return state["tracked"]
        if "ls-files" in args:
            return state["untracked"]
        if "submodule" in args:
            return state["submodule"]
        raise AssertionError(args)

    monkeypatch.setattr(sih_baseline, "command", git)
    monkeypatch.setattr(sih_baseline, "verify_version_metadata", lambda source, expected: expected)
    no_extension = lambda *args: pytest.fail("stock source cannot apply or verify experimental patches")
    sih_baseline.verify_source(source, stock_repository, no_extension, firmware_policy="stock")
    state[{"commit": "head", "tracked": "tracked", "untracked": "untracked", "submodule": "submodule"}[tamper]] = {
        "commit": "a" * 40, "tracked": "controller.cpp", "untracked": "extra.cpp",
        "submodule": "+" + "e" * 40 + " src/lib/cdrstream/cyclonedds",
    }[tamper]
    with pytest.raises(ValueError):
        sih_baseline.verify_source(source, stock_repository, no_extension, firmware_policy="stock")


def test_stock_cli_keeps_ros_and_extension_preparation_out_of_build(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(build_native_guidance.sys, "argv", [
        "build_native_guidance.py", "--target", "sih", "--firmware-policy", "stock",
        "--prepare-only", "--px4-source", str(tmp_path), "--output-dir", str(tmp_path / "out"),
    ])
    monkeypatch.setattr(build_native_guidance, "prepare_sources", lambda *args: pytest.fail("ROS preparation"))
    monkeypatch.setattr(sih_baseline, "build_sih", lambda *args, **kwargs: calls.append(kwargs))
    build_native_guidance.main()
    assert calls[0]["firmware_policy"] == "stock"


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
    import shutil

    lock_path = repository / "native/dependencies.lock.json"
    lock = json.loads(lock_path.read_text())
    spec = json.loads((sih_baseline.ROOT / "native/dependencies.lock.json").read_text())["gazebo_build"]
    spec.update(toolchain_image=lock["sih_build"]["toolchain_image"],
                runtime_image=lock["sih_build"]["runtime_image"])
    spec.pop("microcdr", None)
    lock["gazebo_build"] = spec
    lock_path.write_text(json.dumps(lock))
    shutil.copytree(sih_baseline.ROOT / "native/gazebo/variants", repository / "native/gazebo/variants")
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
    assert plan["command"][:4] == ["make", "px4_sitl_default", "-j2", "j=2"]
    assert "gz_quadtailsitter" not in plan["command"]
    recipe = (output / "context/Dockerfile.firmware").read_text()
    assert "RUN DONT_RUN=1 GZ_DISTRO=harmonic make px4_sitl_default -j2" in recipe
    assert "gz sim" not in recipe
    assert not (output / "gazebo-build-manifest.json").exists()


@pytest.mark.parametrize("variant", sih_baseline.GAZEBO_RESOURCE_VARIANTS)
def test_gazebo_mock_build_binds_resources_and_is_not_a_sih_manifest(gazebo_repository, tmp_path, monkeypatch, variant):
    source = tmp_path / "source"
    source.mkdir()
    staged = tmp_path / "resources"
    resources = gazebo_resources(staged)
    if variant != "stock":
        raw = (Path(__file__).resolve().parents[1] / "fixtures/native_gazebo/airspeed-model.sdf").read_bytes()
        (staged / "models/airspeed/model.sdf").write_bytes(raw)
        resource = source / "Tools/simulation/gz/models/airspeed/model.sdf"
        resource.parent.mkdir(parents=True)
        resource.write_bytes(raw)
        resources["models"] = sih_baseline.tree_manifest(staged / "models")
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
                firmware, spec = sih_baseline.authority(gazebo_repository, simulator="gazebo", resource_variant=variant)
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
                                      repository=gazebo_repository, simulator="gazebo", resource_variant=variant)
    manifest = json.loads(path.read_text())
    assert path.name == "gazebo-build-manifest.json"
    assert manifest["kind"] == "pixeagle_gazebo_build"
    assert not manifest["hardware_qualified"] and not manifest["response_qualified"]
    assert manifest["source"]["gazebo_resources"] == resources
    assert manifest["artifacts"]["bin"]["px4"]["sha256"] == sih_baseline.digest(output / "packaged/bin/px4")
    for directory in ("bin", "etc"):
        assert manifest["artifacts"][directory] == sih_baseline.tree_manifest(output / "packaged" / directory)
    if variant != "stock":
        descriptor = manifest["build"]["resource_variant"]
        assert manifest["artifacts"]["gazebo"][descriptor["resource"]]["sha256"] == descriptor["packaged_sha256"]
        assert resources["models"]["airspeed/model.sdf"]["sha256"] == descriptor["source_sha256"]
    assert "plugins/libAirSpeedPlugin.so" in manifest["artifacts"]["gazebo"]
    assert sum(args[:2] == ("docker", "build") for args in commands) == 2
    runtime = (output / "packaged/Dockerfile").read_text()
    assert "org.pixeagle.gazebo.recipe" in runtime and "org.pixeagle.sih.recipe" not in runtime
    assert "GZ_SIM_SERVER_CONFIG_PATH=/opt/px4/gazebo/server.config" in runtime
    assert sih_baseline.validate_build_manifest(path, repository=gazebo_repository, simulator="gazebo")[
        "kind"] == "verified_gazebo_source_build"
    with pytest.raises(ValueError, match="reviewed build recipe|variants require the Gazebo build"):
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


def test_sih_generated_dockerfiles_only_add_native_job_forwarding(repository, tmp_path, monkeypatch):
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
        "RUN DONT_RUN=1 make px4_sitl_sih -j2 j=2\n"
    )
    assert json.loads((output / "build-plan.json").read_text())["qualification"] == (
        "build inputs only; no SIH response qualification")


def test_px4_make_forwards_the_bounded_job_count_to_ninja(gazebo_repository, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(sih_baseline, "verify_source", lambda *args, **kwargs: {"submodules": []})
    monkeypatch.setattr(sih_baseline, "command", lambda *args: pytest.fail("no Docker or compiler command"))
    path = sih_baseline.build_simulator(source, tmp_path / "prepared", prepare_only=True,
        verify_extension=lambda *args: None, repository=gazebo_repository, simulator="gazebo")
    argv = json.loads(path.read_text())["command"]
    makefile = Path(__file__).resolve().parents[1] / "fixtures/native_gazebo/px4-ninja-jobs.mk"
    probe = ["make", "--no-print-directory", "-f", str(makefile), "show", "NO_NINJA_BUILD=1", "NINJA_BUILD=fixture"]
    assert subprocess.check_output([*probe, "-j2"], text=True).strip() == ""
    forwarded = [arg for arg in argv if arg.startswith(("-j", "j="))]
    assert forwarded == ["-j2", "j=2"]
    assert subprocess.check_output([*probe, *forwarded], text=True).strip() == "-j2"


def test_no_pitot_derivative_removes_only_the_sensor_and_preserves_plant_bytes(gazebo_repository):
    import xml.etree.ElementTree as ET

    firmware, stock = sih_baseline.authority(gazebo_repository, simulator="gazebo")
    same_firmware, selected = sih_baseline.authority(gazebo_repository, simulator="gazebo",
        resource_variant="quadtailsitter-no-pitot-v1")
    variant = selected["resource_variant"]
    raw = (Path(__file__).resolve().parents[1] / "fixtures/native_gazebo/airspeed-model.sdf").read_bytes()
    derived = sih_baseline.derived_gazebo_resource(raw, variant)
    assert firmware == same_firmware
    assert "resource_variant" not in stock
    assert sih_baseline.recipe_fingerprint(firmware, stock) != sih_baseline.recipe_fingerprint(firmware, selected)
    assert derived == raw.replace(variant["remove_xml"].encode(), b"", 1)
    assert len(raw) - len(derived) == 256
    assert not ET.fromstring(derived).findall(".//sensor")
    assert ET.fromstring(derived).find(".//mass").text == "0.015"
    assert sih_baseline.gazebo_resource_variant(gazebo_repository, "stock") is None


@pytest.mark.parametrize("change", ["unknown", "wrong_simulator", "wrong_commit", "resource", "extra",
                                     "wrong_sensor", "bad_xml", "symlink", "stock_lock_override"])
def test_no_pitot_selection_refuses_unknown_or_unreviewed_variants(gazebo_repository, change):
    name = "quadtailsitter-no-pitot-v1"
    path = gazebo_repository / "native/gazebo/variants" / (name + ".json")
    variant = json.loads(path.read_text())
    simulator = "gazebo"
    if change == "unknown": name = "anything-no-pitot"
    elif change == "wrong_simulator": simulator = "sih"
    elif change == "wrong_commit": variant["gazebo_commit"] = "a" * 40
    elif change == "resource": variant["resource"] = "models/quadtailsitter/model.sdf"
    elif change == "extra": variant["disable_safety"] = True
    elif change == "wrong_sensor": variant["remove_xml"] = '<link name="airspeed_link"/>'
    elif change == "bad_xml": variant["remove_xml"] = '<sensor'
    elif change == "stock_lock_override":
        lock_path = gazebo_repository / "native/dependencies.lock.json"
        lock = json.loads(lock_path.read_text())
        lock["gazebo_build"]["resource_variant"] = variant
        lock_path.write_text(json.dumps(lock))
        name = "stock"
    if change == "symlink":
        original = path.with_suffix(".original")
        path.rename(original)
        path.symlink_to(original.name)
    else:
        path.write_text(json.dumps(variant))
    with pytest.raises(ValueError):
        sih_baseline.authority(gazebo_repository, simulator=simulator, resource_variant=name)


@pytest.mark.parametrize("change", ["source", "missing", "duplicate", "output", "extra_sensor"])
def test_sensor_deletion_rejects_changed_or_ambiguous_inputs(gazebo_repository, change):
    variant = sih_baseline.gazebo_resource_variant(gazebo_repository, "quadtailsitter-no-pitot-v1")
    raw = (Path(__file__).resolve().parents[1] / "fixtures/native_gazebo/airspeed-model.sdf").read_bytes()
    block = variant["remove_xml"].encode()
    if change == "source": raw = raw.replace(b"0.015", b"0.020")
    elif change == "missing": raw = raw.replace(block, b"")
    elif change == "duplicate": raw = raw.replace(block, block * 2)
    elif change == "output": variant["packaged_sha256"] = "a" * 64
    elif change == "extra_sensor": raw = raw.replace(block, block + b'<sensor name="extra" type="air_speed"/>\n')
    if change in ("missing", "duplicate", "extra_sensor"):
        variant["source_sha256"] = hashlib.sha256(raw).hexdigest()
        variant["packaged_sha256"] = hashlib.sha256(raw.replace(block, b"", 1)).hexdigest()
    with pytest.raises(ValueError):
        sih_baseline.derived_gazebo_resource(raw, variant)


@pytest.fixture
def no_pitot_manifest(gazebo_repository, tmp_path, monkeypatch):
    import shutil

    upstream = tmp_path / "upstream"
    expected = gazebo_resources(upstream)
    raw = (Path(__file__).resolve().parents[1] / "fixtures/native_gazebo/airspeed-model.sdf").read_bytes()
    (upstream / "models/airspeed/model.sdf").write_bytes(raw)
    expected["models"] = sih_baseline.tree_manifest(upstream / "models")
    source = {"submodules": [], "gazebo_resources": expected}
    packaged = tmp_path / "package"
    packaged_files(packaged)
    (packaged / "etc/init.d-posix/airframes/4018_gz_quadtailsitter").write_text("4018")
    shutil.copytree(upstream, packaged / "gazebo")
    (packaged / "gazebo/plugins").mkdir()
    for name in ("libOpticalFlowSystem.so", "libOpticalFlow.so", "libAirSpeedPlugin.so", "libGstCameraSystem.so"):
        (packaged / "gazebo/plugins" / name).write_bytes(b"compiled fixture plugin")
    firmware, spec = sih_baseline.authority(gazebo_repository, simulator="gazebo", resource_variant="quadtailsitter-no-pitot-v1")
    stock_artifacts = sih_baseline.artifact_manifest(packaged, simulator="gazebo")
    resource = packaged / "gazebo/models/airspeed/model.sdf"
    resource.write_bytes(sih_baseline.derived_gazebo_resource(raw, spec["resource_variant"]))
    artifacts = sih_baseline.artifact_manifest(packaged, simulator="gazebo")
    assert artifacts["bin"] == stock_artifacts["bin"] and artifacts["etc"] == stock_artifacts["etc"]
    assert {key for key in artifacts["gazebo"] if artifacts["gazebo"][key] != stock_artifacts["gazebo"][key]} == {
        "models/airspeed/model.sdf"}
    path = tmp_path / "gazebo-build-manifest.json"
    (tmp_path / "packaged").symlink_to(packaged, target_is_directory=True)
    manifest = {"schema_version": 1, "kind": "pixeagle_gazebo_build", "firmware": firmware,
        "build": spec, "source": source, "artifacts": artifacts,
        "recipe_sha256": sih_baseline.recipe_fingerprint(firmware, spec), "image_id": IMAGE_ID}
    image = {"Id": IMAGE_ID, "Os": "linux", "Architecture": "amd64"}
    def save():
        path.write_text(json.dumps(manifest))
        image["Config"] = {"Labels": sih_baseline.image_labels(manifest["recipe_sha256"], manifest["artifacts"], source, simulator="gazebo")}
    save()
    monkeypatch.setattr(sih_baseline, "command", lambda *args: json.dumps([image]))
    return path, manifest, resource, save


def test_variant_manifest_uses_the_same_strict_image_and_source_verifier(gazebo_repository, no_pitot_manifest):
    path, _, _, _ = no_pitot_manifest
    assert sih_baseline.validate_build_manifest(path, repository=gazebo_repository, simulator="gazebo")["image_id"] == IMAGE_ID


@pytest.mark.parametrize("change", ["unknown", "descriptor", "pretend_stock", "stock_resource", "extra_diff", "source_hash"])
def test_variant_manifest_refuses_substitutions_even_with_rehashed_artifacts(gazebo_repository, no_pitot_manifest, change):
    path, manifest, resource, save = no_pitot_manifest
    if change == "unknown": manifest["build"]["resource_variant"]["name"] = "unknown"
    elif change == "descriptor": manifest["build"]["resource_variant"]["descriptor_sha256"] = "a" * 64
    elif change == "pretend_stock": del manifest["build"]["resource_variant"]
    elif change == "stock_resource":
        resource.write_bytes((Path(__file__).resolve().parents[1] / "fixtures/native_gazebo/airspeed-model.sdf").read_bytes())
    elif change == "extra_diff": resource.with_name("extra.sdf").write_text("extra unreviewed model")
    else: manifest["source"]["gazebo_resources"]["models"]["airspeed/model.sdf"]["sha256"] = "a" * 64
    manifest["artifacts"] = sih_baseline.artifact_manifest(path.parent / "packaged", simulator="gazebo")
    manifest["recipe_sha256"] = sih_baseline.recipe_fingerprint(manifest["firmware"], manifest["build"])
    save()
    with pytest.raises(ValueError):
        sih_baseline.validate_build_manifest(path, repository=gazebo_repository, simulator="gazebo")


def test_gazebo_cli_selects_the_explicit_variant_without_preparing_sources(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(build_native_guidance.sys, "argv", ["builder", "--target", "gazebo", "--prepare-only",
        "--px4-source", str(tmp_path), "--output-dir", str(tmp_path / "out"),
        "--gazebo-resource-variant", "quadtailsitter-no-pitot-v1"])
    monkeypatch.setattr(sih_baseline, "build_simulator", lambda *args, **kwargs: calls.append(kwargs))
    build_native_guidance.main()
    assert calls[0]["resource_variant"] == "quadtailsitter-no-pitot-v1"


@pytest.mark.parametrize("target", ["sih", "contracts", "px4-functional"])
def test_no_pitot_cli_rejects_other_targets_before_any_preparation(monkeypatch, tmp_path, target):
    monkeypatch.setattr(build_native_guidance.sys, "argv", ["builder", "--target", target,
        "--output-dir", str(tmp_path / "unused"), "--gazebo-resource-variant", "quadtailsitter-no-pitot-v1"])
    with pytest.raises(SystemExit):
        build_native_guidance.main()
    assert not (tmp_path / "unused").exists()


def test_explicit_frozen_builder_authority_can_validate_but_cannot_build_with_current_code(repository, tmp_path, monkeypatch):
    path, manifest, image = build_manifest(repository, tmp_path / "old-build")
    (repository / "tools/sih_baseline.py").write_bytes(b"exact retained historical builder bytes\n")
    manifest["recipe_sha256"] = sih_baseline.recipe_fingerprint(manifest["firmware"], manifest["build"], repository=repository)
    path.write_text(json.dumps(manifest))
    image["Config"]["Labels"] = sih_baseline.image_labels(manifest["recipe_sha256"], manifest["artifacts"], manifest["source"])
    monkeypatch.setattr(sih_baseline, "command", lambda *args: json.dumps([image]))
    assert sih_baseline.validate_build_manifest(path, repository=repository)["recipe_sha256"] == manifest["recipe_sha256"]
    with pytest.raises(ValueError, match="reviewed build recipe"):
        sih_baseline.validate_build_manifest(path)
    with pytest.raises(ValueError, match="mixed builder versions"):
        sih_baseline.build_simulator(tmp_path / "source", tmp_path / "unused", prepare_only=True,
                                    verify_extension=lambda *args: None, repository=repository)
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize("change", ["missing", "changed"])
def test_variant_requires_the_exact_upstream_resource_before_creating_output(gazebo_repository, tmp_path, monkeypatch, change):
    source = tmp_path / "source"
    source.mkdir()
    if change == "changed":
        resource = source / "Tools/simulation/gz/models/airspeed/model.sdf"
        resource.parent.mkdir(parents=True)
        resource.write_text("different sensor or physics")
    monkeypatch.setattr(sih_baseline, "verify_source", lambda *args, **kwargs: {"submodules": []})
    monkeypatch.setattr(sih_baseline, "command", lambda *args: pytest.fail("no external command permitted"))
    with pytest.raises((FileNotFoundError, ValueError)):
        sih_baseline.build_simulator(source, tmp_path / "unused", prepare_only=True,
            verify_extension=lambda *args: None, repository=gazebo_repository, simulator="gazebo",
            resource_variant="quadtailsitter-no-pitot-v1")
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize("change", ["missing", "symlink"])
def test_fingerprint_requires_regular_builder_bytes_in_explicit_authority(repository, change):
    builder = repository / "tools/sih_baseline.py"
    builder.unlink()
    if change == "symlink": builder.symlink_to(Path(sih_baseline.__file__))
    firmware, spec = sih_baseline.authority(repository)
    with pytest.raises(ValueError, match="regular builder source"):
        sih_baseline.recipe_fingerprint(firmware, spec, repository=repository)


@pytest.mark.parametrize("metadata", [None, [], 123, "stock", False, {},
    {"build": None}, {"build": []}, {"build": 123}, {"build": "stock"}, {"build": False}])
def test_malformed_manifest_objects_refuse_before_authority_or_external_calls(tmp_path, monkeypatch, metadata):
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(metadata))
    monkeypatch.setattr(sih_baseline, "authority", lambda *a, **k: pytest.fail("metadata must fail before authority lookup"))
    monkeypatch.setattr(sih_baseline, "command", lambda *a: pytest.fail("no external command permitted"))
    monkeypatch.setattr(sih_baseline, "inspect_image", lambda *a, **k: pytest.fail("no image query permitted"))
    with pytest.raises(ValueError, match="object"):
        sih_baseline.validate_build_manifest(path, simulator="gazebo")
