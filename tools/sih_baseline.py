"""Build and verify explicitly selected SIH/Gazebo artifacts; never start PX4."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
LABEL = "org.pixeagle.sih"
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
GAZEBO_SERVER_CONFIG = "src/modules/simulation/gz_bridge/server.config"
GAZEBO_RESOURCE_VARIANTS = ("stock", "quadtailsitter-no-pitot-v1")


def gazebo_resource_variant(repository: Path, name: str) -> dict | None:
    """Load one reviewed instrumentation-only derivative, never a model override."""
    if name == "stock":
        return None
    if name not in GAZEBO_RESOURCE_VARIANTS:
        raise ValueError("Unknown Gazebo resource variant")
    path = repository / "native/gazebo/variants" / (name + ".json")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing regular Gazebo resource variant descriptor")
    variant = json.loads(path.read_text())
    if (not isinstance(variant, dict)
            or set(variant) != {"schema_version", "name", "resource", "gazebo_commit", "source_sha256",
                        "packaged_sha256", "remove_xml"}
            or type(variant["schema_version"]) is not int or variant["schema_version"] != 1 or variant["name"] != name
            or variant["resource"] != "models/airspeed/model.sdf"
            or not isinstance(variant["remove_xml"], str) or not variant["remove_xml"]
            or not all(isinstance(variant[key], str) and re.fullmatch(r"[0-9a-f]{64}", variant[key])
                       for key in ("source_sha256", "packaged_sha256"))):
        raise ValueError("Invalid Gazebo resource variant descriptor")
    try:
        sensor = ET.fromstring(variant["remove_xml"])
    except ET.ParseError as exc:
        raise ValueError("Gazebo variant sensor block is not XML") from exc
    if sensor.tag != "sensor" or sensor.attrib != {"name": "air_speed", "type": "air_speed"}:
        raise ValueError("Gazebo variant must remove only the airspeed sensor")
    return {**variant, "descriptor_sha256": digest(path)}


def derived_gazebo_resource(raw: bytes, variant: dict) -> bytes:
    """Delete the exact reviewed sensor block while preserving all other bytes."""
    if hashlib.sha256(raw).hexdigest() != variant["source_sha256"]:
        raise ValueError("Gazebo variant source resource checksum mismatch")
    block = variant["remove_xml"].encode()
    if raw.count(block) != 1:
        raise ValueError("Gazebo variant sensor block is missing or ambiguous")
    derived = raw.replace(block, b"", 1)
    if hashlib.sha256(derived).hexdigest() != variant["packaged_sha256"]:
        raise ValueError("Gazebo variant derived resource checksum mismatch")
    if ET.fromstring(derived).findall(".//sensor"):
        raise ValueError("Gazebo no-pitot resource still contains a sensor")
    return derived


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def build_image(arguments: list[str], log: Path) -> None:
    try:
        output = command(*arguments)
    except subprocess.CalledProcessError as exc:
        log.write_text(exc.output or "")
        raise
    log.write_text(output + "\n")


def authority(repository: Path = ROOT, *, simulator: str = "sih",
              resource_variant: str = "stock") -> tuple[dict, dict]:
    if simulator not in ("sih", "gazebo"):
        raise ValueError("Unsupported simulator build recipe")
    if resource_variant != "stock" and simulator != "gazebo":
        raise ValueError("Gazebo resource variants require the Gazebo build")
    lock = json.loads((repository / "native/dependencies.lock.json").read_text())
    extension_path = repository / "native/px4/extension.json"
    extension = json.loads(extension_path.read_text())
    if extension["baseline_commit"] != lock["reference_px4_commit"]:
        raise ValueError("SIH firmware and extension baseline pins disagree")
    for name, checksum in extension["patches"].items():
        if digest(repository / "native/px4" / name) != checksum:
            raise ValueError(f"SIH extension patch checksum mismatch: {name}")
    spec = dict(lock[simulator + "_build"])
    if "resource_variant" in spec:
        raise ValueError("Select Gazebo resource variants explicitly, outside the stock recipe")
    target = "px4_sitl_sih" if simulator == "sih" else "px4_sitl_default"
    if spec["platform"] != "linux/amd64" or spec["target"] != target:
        raise ValueError("Unsupported simulator build platform or target")
    if simulator == "gazebo":
        if (spec.get("distribution"), spec.get("model"), spec.get("world"), spec.get("airframe_id")) != (
                "harmonic", "quadtailsitter", "default", 4018):
            raise ValueError("Unsupported Gazebo distribution/model/world/airframe")
        required = {"Tools/simulation/gz", "src/modules/simulation/gz_plugins/optical_flow/PX4-OpticalFlow"}
        pins = spec.get("submodule_pins", {})
        if (not required.issubset(spec.get("submodules", [])) or set(pins) != required
                or any(not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{40}", pin)
                       for pin in pins.values())):
            raise ValueError("Gazebo model/plugin resource submodules require exact commit pins")
        variant = gazebo_resource_variant(repository, resource_variant)
        if variant is not None:
            if variant["gazebo_commit"] != pins["Tools/simulation/gz"]:
                raise ValueError("Gazebo variant resource commit differs from the locked source")
            spec["resource_variant"] = variant
    for key in ("toolchain_image", "runtime_image"):
        value = spec.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", value):
            raise ValueError(f"{simulator} {key} requires an immutable image pin; prepare and lock dependencies first")
    firmware = {"commit": lock["reference_px4_commit"], "extension_sha256": digest(extension_path),
                "patches": extension["patches"]}
    if "reference_px4_version" in lock:
        firmware["version"] = lock["reference_px4_version"]
    return firmware, spec


def recipe_fingerprint(firmware: dict, spec: dict, *, repository: Path | None = None) -> str:
    builder = Path(__file__) if repository is None else repository / "tools/sih_baseline.py"
    if builder.is_symlink() or not builder.is_file():
        raise ValueError("A regular builder source is required in the selected build authority")
    return json_digest({"firmware": firmware, "build": spec, "builder_sha256": digest(builder)})


def verify_version_metadata(source: Path, expected: dict) -> dict:
    """Use pinned upstream tag ancestry, never a fabricated firmware version."""
    fields = {"describe", "tag", "tag_object", "tag_commit"}
    if (not isinstance(expected, dict) or set(expected) != fields
            or any(not isinstance(expected[key], str) or not expected[key] for key in fields)
            or not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[A-Za-z0-9.]+)?", expected["tag"])
            or re.match(r"v0\.0\.0(?:$|-)", expected["tag"])
            or any(not re.fullmatch(r"[0-9a-f]{40}", expected[key]) for key in ("tag_object", "tag_commit"))):
        raise ValueError("Pinned PX4 release metadata is missing or unknown")
    prefix = ("git", "-C", str(source))
    try:
        actual = {
            "describe": command(*prefix, "describe", "--exclude", "ext/*", "--tags", "--match", "v[0-9]*"),
            "tag": command(*prefix, "describe", "--exclude", "ext/*", "--abbrev=0", "--tags", "--match", "v[0-9]*"),
            "tag_object": command(*prefix, "rev-parse", "refs/tags/" + expected["tag"]),
            "tag_commit": command(*prefix, "rev-parse", "refs/tags/" + expected["tag"] + "^{commit}"),
        }
        command(*prefix, "merge-base", "--is-ancestor", expected["tag_commit"], "HEAD")
    except subprocess.CalledProcessError as error:
        raise ValueError("PX4 release ancestry is unavailable; refusing v0.0.0 fallback") from error
    if actual != expected:
        raise ValueError("PX4 release metadata differs from the pinned upstream ancestry")
    return actual


def verify_source(source: Path, repository: Path, verify_extension, *, simulator: str = "sih") -> dict:
    """Require the reviewed patch and exact, clean recursive submodule revisions."""
    if not (source / ".git").is_dir():
        raise ValueError("SIH needs a standalone Git checkout, not a linked worktree or binary directory")
    if (source / ".git/objects/info/alternates").exists():
        raise ValueError("SIH source Git objects must be self-contained")
    extension = repository / "native/px4"
    verify_extension(source, extension)
    manifest = json.loads((extension / "extension.json").read_text())
    approved = set(manifest["files"]) | set(manifest.get("deleted_files", []))
    changed = command("git", "-c", "gc.auto=0", "-C", str(source), "diff", "HEAD", "--name-only",
                      "--ignore-submodules=none").splitlines()
    untracked = command("git", "-C", str(source), "ls-files", "--others", "--exclude-standard").splitlines()
    unexpected = (set(changed) | set(untracked)) - approved
    if unexpected:
        raise ValueError("Unreviewed SIH source changes: " + ", ".join(sorted(unexpected)))
    submodules = command("git", "-C", str(source), "submodule", "status", "--recursive")
    firmware, spec = authority(repository, simulator=simulator)
    required = spec.get("submodules", [])
    initialized = []
    missing = set(required)
    for line in submodules.splitlines():
        status = line[0] if line[0] in "-+U " else " "
        fields = (line[1:] if line[0] in "-+U " else line).split()
        path = fields[1]
        if status in "+U" or (status == "-" and any(path == item or path.startswith(item + "/") for item in required)):
            raise ValueError("SIH submodules must be initialized at the pinned Git revisions")
        if simulator == "gazebo" and path in spec["submodule_pins"] and fields[0] != spec["submodule_pins"][path]:
            raise ValueError(f"Gazebo resource submodule differs from its locked commit: {path}")
        if status != "-":
            missing.discard(path)
            initialized.append(" ".join(fields))
    if missing:
        raise ValueError("Missing SIH submodules: " + ", ".join(sorted(missing)))
    provenance = {"submodules": initialized}
    if "version" in firmware:
        provenance["version"] = verify_version_metadata(source, firmware["version"])
    if simulator == "gazebo":
        resources = source / "Tools/simulation/gz"
        for relative in ("models/quadtailsitter/model.sdf", "models/airspeed/model.sdf", "worlds/default.sdf"):
            if not (resources / relative).is_file():
                raise ValueError(f"Missing pinned Gazebo resource: {relative}")
        provenance["gazebo_resources"] = {"models": tree_manifest(resources / "models"),
                                          "worlds": tree_manifest(resources / "worlds"),
                                          "server_config_sha256": digest(source / GAZEBO_SERVER_CONFIG)}
    return provenance


def prepare_microcdr(spec: dict, cache: Path) -> Path:
    """Supply the upstream client's exact external dependency without online compilation."""
    pin = spec["microcdr"]
    source = cache / ("Micro-CDR-" + pin["commit"])
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        command("git", "clone", "--no-checkout", pin["repository"], str(source))
        command("git", "-C", str(source), "checkout", "--detach", pin["commit"])
    head = command("git", "-C", str(source), "rev-parse", "HEAD")
    tag = command("git", "-C", str(source), "rev-parse", pin["tag"] + "^{commit}")
    if head != pin["commit"] or tag != head or command("git", "-C", str(source), "status", "--porcelain"):
        raise ValueError("Micro-CDR source differs from the locked dependency")
    if not (source / ".git").is_dir() or (source / ".git/objects/info/alternates").exists():
        raise ValueError("Micro-CDR Git source must be self-contained")
    return source


def tree_manifest(root: Path) -> dict:
    """Include aliases without following links outside the packaged tree."""
    result = {}
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Missing regular SIH artifact directory: {root}")
    for path in sorted(root.rglob("*")):
        name = str(path.relative_to(root))
        if path.is_symlink():
            target = path.readlink()
            if target.is_absolute() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError(f"Invalid SIH artifact alias: {name}")
            result[name] = {"link": str(target)}
        elif path.is_file():
            result[name] = {"sha256": digest(path), "executable": bool(path.stat().st_mode & 0o111)}
        elif not path.is_dir():
            raise ValueError(f"Unsupported SIH artifact: {name}")
    if not result:
        raise ValueError(f"Empty SIH artifact directory: {root}")
    return result


def artifact_manifest(packaged: Path, *, simulator: str = "sih") -> dict:
    binary = packaged / "bin/px4"
    if binary.is_symlink() or not binary.is_file() or not binary.stat().st_mode & 0o111:
        raise ValueError("SIH firmware executable is missing")
    with binary.open("rb") as stream:
        header = stream.read(20)
    if header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\x3e\x00":
        raise ValueError("SIH firmware must be a Linux amd64 ELF executable")
    airframe = "10040_sihsim_quadx" if simulator == "sih" else "4018_gz_quadtailsitter"
    for name in ("bin/px4-alias.sh", "etc/init.d-posix/rcS", f"etc/init.d-posix/airframes/{airframe}"):
        if not (packaged / name).is_file():
            raise ValueError(f"Matching SIH runtime artifact is missing: {name}")
    artifacts = {"binary_sha256": digest(binary), "bin": tree_manifest(packaged / "bin"),
                 "etc": tree_manifest(packaged / "etc")}
    if simulator == "gazebo":
        for relative in ("models/quadtailsitter/model.sdf", "models/airspeed/model.sdf", "worlds/default.sdf",
                         "server.config", "plugins/libOpticalFlowSystem.so", "plugins/libOpticalFlow.so",
                         "plugins/libAirSpeedPlugin.so", "plugins/libGstCameraSystem.so"):
            if not (packaged / "gazebo" / relative).is_file():
                raise ValueError(f"Missing Gazebo runtime resource: {relative}")
        artifacts["gazebo"] = tree_manifest(packaged / "gazebo")
    return artifacts


def verify_packaged_resources(artifacts: dict, source: dict, *, variant: dict | None = None) -> None:
    """Resource files must survive compilation/packaging without substitutions."""
    expected = source.get("gazebo_resources")
    if not isinstance(expected, dict):
        raise ValueError("Gazebo source resource provenance is missing")
    bundled = artifacts["gazebo"]
    for directory in ("models", "worlds"):
        actual = {name.removeprefix(directory + "/"): value for name, value in bundled.items()
                  if name.startswith(directory + "/")}
        expected_files = dict(expected.get(directory, {}))
        if variant is not None and directory == "models":
            name = variant["resource"].removeprefix("models/")
            if expected_files.get(name) != {"sha256": variant["source_sha256"], "executable": False}:
                raise ValueError("Gazebo variant lacks its exact upstream resource provenance")
            expected_files[name] = {"sha256": variant["packaged_sha256"], "executable": False}
        if actual != expected_files:
            raise ValueError(f"Packaged Gazebo {directory} differ from the verified source")
    if bundled["server.config"].get("sha256") != expected.get("server_config_sha256"):
        raise ValueError("Packaged Gazebo server configuration differs from the verified source")


def image_labels(fingerprint: str, artifacts: dict, source: dict, *, simulator: str = "sih") -> dict:
    label = LABEL if simulator == "sih" else "org.pixeagle.gazebo"
    return {f"{label}.recipe": fingerprint, f"{label}.binary": artifacts["binary_sha256"],
            f"{label}.artifacts": json_digest(artifacts), f"{label}.source": json_digest(source)}


def inspect_image(image: str, *, pinned_input: bool = False) -> dict:
    info = json.loads(command("docker", "image", "inspect", image))[0]
    if info.get("Os") != "linux" or info.get("Architecture") != "amd64":
        raise ValueError("SIH images must be Linux amd64")
    if pinned_input and not any(value.endswith("@" + image.rsplit("@", 1)[1])
                                for value in (info.get("RepoDigests") or [])):
        raise ValueError(f"SIH input image digest is unavailable: {image}")
    if not IMAGE_ID.fullmatch(info.get("Id", "")):
        raise ValueError("SIH image has no immutable image ID")
    return info


def validate_build_manifest(path: Path, *, repository: Path = ROOT, simulator: str = "sih") -> dict:
    path = path.expanduser().resolve()
    manifest = json.loads(path.read_text())
    if not isinstance(manifest, dict) or not isinstance(manifest.get("build"), dict):
        raise ValueError("Simulation build manifest and build metadata must be objects")
    declared_variant = manifest.get("build", {}).get("resource_variant")
    variant_name = declared_variant.get("name") if isinstance(declared_variant, dict) else "stock"
    firmware, spec = authority(repository, simulator=simulator, resource_variant=variant_name)
    fingerprint = recipe_fingerprint(firmware, spec, repository=repository)
    if (manifest.get("schema_version") != 1 or manifest.get("kind") != f"pixeagle_{simulator}_build"
            or manifest.get("firmware") != firmware or manifest.get("build") != spec
            or manifest.get("recipe_sha256") != fingerprint):
        raise ValueError("SIH build manifest does not match the reviewed build recipe")
    artifacts = artifact_manifest(path.parent / "packaged", simulator=simulator)
    if artifacts != manifest.get("artifacts"):
        raise ValueError("SIH packaged binary or ROMFS differs from the build manifest")
    source = manifest.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("submodules"), list):
        raise ValueError("SIH source provenance is missing")
    if simulator == "gazebo":
        verify_packaged_resources(artifacts, source, variant=spec.get("resource_variant"))
    image_id = manifest.get("image_id", "")
    if not isinstance(image_id, str) or not IMAGE_ID.fullmatch(image_id):
        raise ValueError("SIH build manifest requires an immutable image ID")
    info = inspect_image(image_id)
    labels = info.get("Config", {}).get("Labels") or {}
    if info["Id"] != image_id or any(labels.get(key) != value
                                     for key, value in image_labels(fingerprint, artifacts, source, simulator=simulator).items()):
        raise ValueError("SIH image is not bound to the packaged build artifacts")
    return {"kind": "verified_source_build" if simulator == "sih" else "verified_gazebo_source_build",
            "image_id": image_id, "manifest": str(path),
            "manifest_sha256": digest(path), "recipe_sha256": fingerprint,
            "firmware": firmware, "binary_sha256": artifacts["binary_sha256"]}


def build_sih(source: Path, output: Path, *, prepare_only: bool, verify_extension,
              repository: Path = ROOT, cache: Path | None = None) -> Path:
    return build_simulator(source, output, prepare_only=prepare_only, verify_extension=verify_extension,
                           repository=repository, cache=cache)


def build_simulator(source: Path, output: Path, *, prepare_only: bool, verify_extension,
                    repository: Path = ROOT, cache: Path | None = None, simulator: str = "sih",
                    resource_variant: str = "stock") -> Path:
    source, output = source.expanduser().resolve(), output.expanduser().resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Keep SIH build evidence separate from the source checkout")
    firmware, spec = authority(repository, simulator=simulator, resource_variant=resource_variant)
    fingerprint = recipe_fingerprint(firmware, spec, repository=repository)
    if digest(repository / "tools/sih_baseline.py") != digest(Path(__file__)):
        raise ValueError("Run the builder from the selected build authority; mixed builder versions cannot build")
    variant = spec.get("resource_variant")
    selection = {} if simulator == "sih" else {"simulator": simulator}
    provenance = verify_source(source, repository, verify_extension, **selection)
    if variant is not None:
        derived_gazebo_resource((source / "Tools/simulation/gz" / variant["resource"]).read_bytes(), variant)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new SIH build output directory; existing evidence is never overwritten")
    output.mkdir(parents=True, exist_ok=True)
    context = output / "context"
    context.mkdir()
    # Excluding build outputs forces compilation from sources, even with a warm Docker/ccache cache.
    def ignored(directory, names):
        return {name for name in names if name in {"__pycache__", ".venv"}
                or (Path(directory) == source and name == "build")}

    shutil.copytree(source, context / "source", symlinks=True, ignore=ignored)
    copied_provenance = verify_source(context / "source", repository, verify_extension, **selection)
    if copied_provenance != provenance:
        raise ValueError("SIH source changed while preparing the build")
    dependency_setup = ""
    if "microcdr" in spec:
        dependency = prepare_microcdr(spec, cache or Path.home() / ".cache/pixeagle-native-guidance")
        shutil.copytree(dependency, context / "microcdr", symlinks=True)
        dependency_setup = (
            "COPY microcdr/ /work/microcdr/\n"
            'RUN git config --global protocol.file.allow always && '
            'git config --global url."file:///work/microcdr".insteadOf '
            + shlex.quote(spec["microcdr"]["repository"]) + "\n"
        )
    build_command = ["make", spec["target"], "-j2", "j=2"]
    if spec.get("submodules"):
        build_command.append('CMAKE_ARGS=-DPX4_GIT_SUBMODULES="' + ";".join(spec["submodules"]) + '"')
    (context / "Dockerfile.firmware").write_text(
        f"FROM {spec['toolchain_image']}\n"
        "COPY source/ /work/px4-simulation-source/\n"
        "WORKDIR /work/px4-simulation-source\n"
        + dependency_setup +
        "RUN cmake --version && ninja --version && c++ --version && python3 --version\n"
        "RUN DONT_RUN=1 " + ("GZ_DISTRO=harmonic " if simulator == "gazebo" else "")
        + shlex.join(build_command) + "\n"
        + ("RUN mkdir /work/gazebo-plugins && cp build/px4_sitl_default/src/modules/simulation/gz_plugins/*.so* "
           "/work/gazebo-plugins/\n" if simulator == "gazebo" else "")
    )
    plan = {"firmware": firmware, "build": spec, "source": provenance,
            "recipe_sha256": fingerprint, "command": build_command,
            "prepare_only": prepare_only, "qualification": f"build inputs only; no {simulator.upper()} response qualification"}
    (output / "build-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    if prepare_only:
        print(f"{simulator.upper()} source build prepared: {output}; no image built or baseline adopted")
        return output / "build-plan.json"
    inspect_image(spec["toolchain_image"], pinned_input=True)
    inspect_image(spec["runtime_image"], pinned_input=True)
    iid = output / "firmware-image-id.txt"
    build_image(["docker", "build", "--network=none", "--pull=false", "--platform", spec["platform"],
                 "--file", str(context / "Dockerfile.firmware"), "--iidfile", str(iid), str(context)],
                output / "firmware-build.log")
    builder_id = iid.read_text().strip()
    if not IMAGE_ID.fullmatch(builder_id):
        raise ValueError("SIH compiler image ID is invalid")
    container = command("docker", "create", "--entrypoint", "/bin/true", builder_id)
    packaged = output / "packaged"
    packaged.mkdir()
    try:
        for directory in ("bin", "etc"):
            command("docker", "cp", f"{container}:/work/px4-simulation-source/build/{spec['target']}/{directory}",
                    str(packaged / directory))
        if simulator == "gazebo":
            resources = packaged / "gazebo"
            resources.mkdir()
            for directory in ("models", "worlds"):
                command("docker", "cp", f"{container}:/work/px4-simulation-source/Tools/simulation/gz/{directory}",
                        str(resources / directory))
            command("docker", "cp", f"{container}:/work/px4-simulation-source/{GAZEBO_SERVER_CONFIG}",
                    str(resources / "server.config"))
            command("docker", "cp", f"{container}:/work/gazebo-plugins", str(resources / "plugins"))
    finally:
        command("docker", "rm", container)
    artifacts = artifact_manifest(packaged, **selection)
    if simulator == "gazebo":
        verify_packaged_resources(artifacts, provenance)
        if variant is not None:
            resource = packaged / "gazebo" / variant["resource"]
            if resource.is_symlink():
                raise ValueError("Gazebo variant requires a regular packaged resource")
            resource.write_bytes(derived_gazebo_resource(resource.read_bytes(), variant))
            artifacts = artifact_manifest(packaged, **selection)
            verify_packaged_resources(artifacts, provenance, variant=variant)
    fingerprint = plan["recipe_sha256"]
    labels = "\n".join(f"LABEL {key}={json.dumps(value)}"
                       for key, value in image_labels(fingerprint, artifacts, provenance, **selection).items())
    dockerfile = packaged / "Dockerfile"
    dockerfile.write_text(
        f"FROM {spec['runtime_image']}\n"
        "RUN rm -rf /opt/px4/bin /opt/px4/etc"
        + (" /opt/px4/gazebo" if simulator == "gazebo" else "") + "\n"
        "COPY bin/ /opt/px4/bin/\nCOPY etc/ /opt/px4/etc/\n"
        f"{labels}\n"
        + ("COPY gazebo/ /opt/px4/gazebo/\n"
           "ENV GZ_DISTRO=harmonic HEADLESS=1 PX4_SIM_MODEL=gz_quadtailsitter PX4_GZ_WORLD=default\n"
           "ENV PX4_GZ_MODELS=/opt/px4/gazebo/models PX4_GZ_WORLDS=/opt/px4/gazebo/worlds\n"
           "ENV GZ_SIM_RESOURCE_PATH=/opt/px4/gazebo/models:/opt/px4/gazebo/worlds\n"
           "ENV GZ_SIM_SYSTEM_PLUGIN_PATH=/opt/px4/gazebo/plugins\n"
           "ENV GZ_SIM_SERVER_CONFIG_PATH=/opt/px4/gazebo/server.config\n" if simulator == "gazebo" else "")
        + 'ENTRYPOINT ["/opt/px4/bin/px4"]\n'
        'CMD ["-i", "0", "-w", "/root", "/opt/px4/etc"]\n'
    )
    runtime_iid = output / "runtime-image-id.txt"
    build_image(["docker", "build", "--network=none", "--pull=false", "--platform", spec["platform"],
                 "--iidfile", str(runtime_iid), str(packaged)], output / "runtime-build.log")
    manifest = {"schema_version": 1, "kind": f"pixeagle_{simulator}_build", "firmware": firmware,
                "build": spec, "source": provenance, "recipe_sha256": fingerprint,
                "artifacts": artifacts, "image_id": runtime_iid.read_text().strip(),
                "hardware_qualified": False, "response_qualified": False}
    manifest_path = output / f"{simulator}-build-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    validate_build_manifest(manifest_path, repository=repository, **selection)
    print(f"Verified {simulator.upper()} image build: {manifest_path}; response qualification remains required")
    return manifest_path
