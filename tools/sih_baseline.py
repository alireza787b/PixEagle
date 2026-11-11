"""Build and verify an explicitly selected SIH baseline; never start PX4."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LABEL = "org.pixeagle.sih"
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")


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


def authority(repository: Path = ROOT) -> tuple[dict, dict]:
    lock = json.loads((repository / "native/dependencies.lock.json").read_text())
    extension_path = repository / "native/px4/extension.json"
    extension = json.loads(extension_path.read_text())
    if extension["baseline_commit"] != lock["reference_px4_commit"]:
        raise ValueError("SIH firmware and extension baseline pins disagree")
    for name, checksum in extension["patches"].items():
        if digest(repository / "native/px4" / name) != checksum:
            raise ValueError(f"SIH extension patch checksum mismatch: {name}")
    spec = lock["sih_build"]
    if spec["platform"] != "linux/amd64" or spec["target"] != "px4_sitl_sih":
        raise ValueError("Unsupported SIH build platform or target")
    if any(not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", spec[key])
           for key in ("toolchain_image", "runtime_image")):
        raise ValueError("SIH toolchain and runtime images require immutable digest pins")
    firmware = {"commit": lock["reference_px4_commit"], "extension_sha256": digest(extension_path),
                "patches": extension["patches"]}
    return firmware, spec


def recipe_fingerprint(firmware: dict, spec: dict) -> str:
    return json_digest({"firmware": firmware, "build": spec, "builder_sha256": digest(Path(__file__))})


def verify_source(source: Path, repository: Path, verify_extension) -> dict:
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
    required = authority(repository)[1].get("submodules", [])
    initialized = []
    missing = set(required)
    for line in submodules.splitlines():
        status = line[0] if line[0] in "-+U " else " "
        fields = (line[1:] if line[0] in "-+U " else line).split()
        path = fields[1]
        if status in "+U" or (status == "-" and any(path == item or path.startswith(item + "/") for item in required)):
            raise ValueError("SIH submodules must be initialized at the pinned Git revisions")
        if status != "-":
            missing.discard(path)
            initialized.append(" ".join(fields))
    if missing:
        raise ValueError("Missing SIH submodules: " + ", ".join(sorted(missing)))
    return {"submodules": initialized}


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


def artifact_manifest(packaged: Path) -> dict:
    binary = packaged / "bin/px4"
    if binary.is_symlink() or not binary.is_file() or not binary.stat().st_mode & 0o111:
        raise ValueError("SIH firmware executable is missing")
    with binary.open("rb") as stream:
        header = stream.read(20)
    if header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\x3e\x00":
        raise ValueError("SIH firmware must be a Linux amd64 ELF executable")
    for name in ("bin/px4-alias.sh", "etc/init.d-posix/rcS", "etc/init.d-posix/airframes/10040_sihsim_quadx"):
        if not (packaged / name).is_file():
            raise ValueError(f"Matching SIH runtime artifact is missing: {name}")
    return {"binary_sha256": digest(binary), "bin": tree_manifest(packaged / "bin"),
            "etc": tree_manifest(packaged / "etc")}


def image_labels(fingerprint: str, artifacts: dict, source: dict) -> dict:
    return {f"{LABEL}.recipe": fingerprint, f"{LABEL}.binary": artifacts["binary_sha256"],
            f"{LABEL}.artifacts": json_digest(artifacts), f"{LABEL}.source": json_digest(source)}


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


def validate_build_manifest(path: Path, *, repository: Path = ROOT) -> dict:
    path = path.expanduser().resolve()
    manifest = json.loads(path.read_text())
    firmware, spec = authority(repository)
    fingerprint = recipe_fingerprint(firmware, spec)
    if (manifest.get("schema_version") != 1 or manifest.get("kind") != "pixeagle_sih_build"
            or manifest.get("firmware") != firmware or manifest.get("build") != spec
            or manifest.get("recipe_sha256") != fingerprint):
        raise ValueError("SIH build manifest does not match the reviewed build recipe")
    artifacts = artifact_manifest(path.parent / "packaged")
    if artifacts != manifest.get("artifacts"):
        raise ValueError("SIH packaged binary or ROMFS differs from the build manifest")
    source = manifest.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("submodules"), list):
        raise ValueError("SIH source provenance is missing")
    image_id = manifest.get("image_id", "")
    if not isinstance(image_id, str) or not IMAGE_ID.fullmatch(image_id):
        raise ValueError("SIH build manifest requires an immutable image ID")
    info = inspect_image(image_id)
    labels = info.get("Config", {}).get("Labels") or {}
    if info["Id"] != image_id or any(labels.get(key) != value
                                     for key, value in image_labels(fingerprint, artifacts, source).items()):
        raise ValueError("SIH image is not bound to the packaged build artifacts")
    return {"kind": "verified_source_build", "image_id": image_id, "manifest": str(path),
            "manifest_sha256": digest(path), "recipe_sha256": fingerprint,
            "firmware": firmware, "binary_sha256": artifacts["binary_sha256"]}


def build_sih(source: Path, output: Path, *, prepare_only: bool, verify_extension,
              repository: Path = ROOT, cache: Path | None = None) -> Path:
    source, output = source.expanduser().resolve(), output.expanduser().resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Keep SIH build evidence separate from the source checkout")
    firmware, spec = authority(repository)
    provenance = verify_source(source, repository, verify_extension)
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
    copied_provenance = verify_source(context / "source", repository, verify_extension)
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
    build_command = ["make", "px4_sitl_sih", "-j2"]
    if spec.get("submodules"):
        build_command.append('CMAKE_ARGS=-DPX4_GIT_SUBMODULES="' + ";".join(spec["submodules"]) + '"')
    (context / "Dockerfile.firmware").write_text(
        f"FROM {spec['toolchain_image']}\n"
        "COPY source/ /work/px4-simulation-source/\n"
        "WORKDIR /work/px4-simulation-source\n"
        + dependency_setup +
        "RUN cmake --version && ninja --version && c++ --version && python3 --version\n"
        "RUN DONT_RUN=1 " + shlex.join(build_command) + "\n"
    )
    plan = {"firmware": firmware, "build": spec, "source": provenance,
            "recipe_sha256": recipe_fingerprint(firmware, spec), "command": build_command,
            "prepare_only": prepare_only, "qualification": "build inputs only; no SIH response qualification"}
    (output / "build-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    if prepare_only:
        print(f"SIH source build prepared: {output}; no image built or baseline adopted")
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
            command("docker", "cp", f"{container}:/work/px4-simulation-source/build/px4_sitl_sih/{directory}",
                    str(packaged / directory))
    finally:
        command("docker", "rm", container)
    artifacts = artifact_manifest(packaged)
    fingerprint = plan["recipe_sha256"]
    labels = "\n".join(f"LABEL {key}={json.dumps(value)}"
                       for key, value in image_labels(fingerprint, artifacts, provenance).items())
    dockerfile = packaged / "Dockerfile"
    dockerfile.write_text(
        f"FROM {spec['runtime_image']}\n"
        "RUN rm -rf /opt/px4/bin /opt/px4/etc\n"
        "COPY bin/ /opt/px4/bin/\nCOPY etc/ /opt/px4/etc/\n"
        f"{labels}\n"
        'ENTRYPOINT ["/opt/px4/bin/px4"]\n'
        'CMD ["-i", "0", "-w", "/root", "/opt/px4/etc"]\n'
    )
    runtime_iid = output / "runtime-image-id.txt"
    build_image(["docker", "build", "--network=none", "--pull=false", "--platform", spec["platform"],
                 "--iidfile", str(runtime_iid), str(packaged)], output / "runtime-build.log")
    manifest = {"schema_version": 1, "kind": "pixeagle_sih_build", "firmware": firmware,
                "build": spec, "source": provenance, "recipe_sha256": fingerprint,
                "artifacts": artifacts, "image_id": runtime_iid.read_text().strip(),
                "hardware_qualified": False, "response_qualified": False}
    manifest_path = output / "sih-build-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    validate_build_manifest(manifest_path, repository=repository)
    print(f"Verified SIH image build: {manifest_path}; response qualification remains required")
    return manifest_path
