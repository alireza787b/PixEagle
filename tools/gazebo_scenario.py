"""Explicit runtime scenarios over an unchanged, independently verified Gazebo build.

Repository descriptors select packaged resources; they never redefine build authority,
modify an airframe, publish a scene command, or qualify rendering/flight response.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import xml.etree.ElementTree as ET

SCENARIOS = Path(__file__).resolve().parents[1] / "native/gazebo/scenarios"


def _read_file(packaged: Path, relative: str, entry: dict) -> bytes:
    path = packaged / relative
    if (not isinstance(relative, str) or PurePosixPath(relative).is_absolute()
            or ".." in PurePosixPath(relative).parts or path.is_symlink()
            or not path.resolve().is_relative_to(packaged.resolve()) or not path.is_file()):
        raise ValueError("Gazebo scenario requires regular packaged resources")
    raw = path.read_bytes()
    if entry != {"sha256": hashlib.sha256(raw).hexdigest(), "executable": bool(path.stat().st_mode & 0o111)}:
        raise ValueError(f"Gazebo scenario packaged resource changed: {relative}")
    return raw


def airframe_identity(scenario: dict, files: dict[str, bytes]) -> dict:
    """Read a pinned literal include chain; never execute shell or infer computed values."""
    chain = scenario["airframe_chain"]
    first = f'etc/init.d-posix/airframes/{scenario["airframe_id"]}_gz_{scenario["model"]}'
    if not chain or chain[0] != first or len(set(chain)) != len(chain):
        raise ValueError("Gazebo scenario airframe chain differs from its model/ID")
    visited, expected = [], {"SYS_AUTOSTART": scenario["airframe_id"]}

    def visit(name):
        if name in visited or name not in chain:
            raise ValueError("Gazebo scenario airframe include is cyclic or undeclared")
        visited.append(name)
        depth = 0
        for raw in files[name].decode().splitlines():
            line = raw.split("#", 1)[0].strip()
            if re.match(r"^(?:if|case|for|while|until|function)\b", line):
                depth += 1
            if line.startswith(". ") or line.startswith("source "):
                include = re.fullmatch(r"\.\s+\$\{R\}(etc/[A-Za-z0-9_./-]+)", line)
                if depth or include is None:
                    raise ValueError("Gazebo scenario airframe include must be unconditional and literal")
                visit(include[1])
            for key in scenario["identity_parameters"]:
                if re.search(rf"\b{key}\b", line):
                    value = re.fullmatch(rf"param\s+set-default\s+{key}\s+([+-]?[0-9]+)", line)
                    if depth or key in expected or value is None:
                        raise ValueError(f"Gazebo scenario identity is ambiguous: {key}")
                    expected[key] = int(value[1])
            if re.match(r"^(?:fi|esac|done)\b", line):
                depth -= 1
        if depth != 0:
            raise ValueError("Gazebo scenario airframe shell structure is unsupported")

    visit(first)
    if visited != chain or set(expected) != {"SYS_AUTOSTART", *scenario["identity_parameters"]}:
        raise ValueError("Gazebo scenario airframe identity is incomplete")
    return expected


def verified_scenario(name: str, baseline: dict, manifest: dict) -> dict:
    """Consume the result of the canonical build validator, then check scenario resources."""
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*-v[1-9][0-9]*", name):
        raise ValueError("Unknown Gazebo runtime scenario")
    path = SCENARIOS / (name + ".json")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Unknown Gazebo runtime scenario")
    raw = path.read_bytes()
    value = json.loads(raw)
    fields = {"schema_version", "name", "build_manifest_sha256", "image_id", "binary_sha256",
              "model", "world", "airframe_id", "airframe_chain", "identity_parameters", "models",
              "scene_models", "resources", "spawn_pose", "camera"}
    if (not isinstance(value, dict) or set(value) != fields or type(value["schema_version"]) is not int
            or value["schema_version"] != 1 or value["name"] != name):
        raise ValueError("Invalid Gazebo scenario descriptor")
    if (manifest.get("kind") != "pixeagle_gazebo_build"
            or baseline.get("kind") != "verified_gazebo_source_build"
            or manifest.get("build", {}).get("resource_variant") is not None
            or any(value[key] != baseline.get(key) for key in ("image_id", "binary_sha256"))
            or value["build_manifest_sha256"] != baseline.get("manifest_sha256")
            or manifest.get("image_id") != value["image_id"]
            or manifest.get("artifacts", {}).get("binary_sha256") != value["binary_sha256"]):
        raise ValueError("Gazebo scenario requires its exact verified stock build")
    if (any(not isinstance(value[key], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", value[key])
            for key in ("model", "world")) or type(value["airframe_id"]) is not int
            or value["airframe_id"] <= 0):
        raise ValueError("Invalid Gazebo scenario model/world/airframe")
    pose = value["spawn_pose"]
    if (not isinstance(pose, list) or len(pose) != 6
            or any(type(n) not in (int, float) or not math.isfinite(n) for n in pose)):
        raise ValueError("Gazebo scenario spawn pose requires six finite ENU values")
    for key in ("airframe_chain", "identity_parameters", "models", "scene_models"):
        if (not isinstance(value[key], list) or not value[key] or any(not isinstance(v, str) for v in value[key])
                or len(set(value[key])) != len(value[key])):
            raise ValueError("Invalid Gazebo scenario resource declarations")
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", k) for k in value["identity_parameters"]):
        raise ValueError("Invalid Gazebo scenario parameter name")
    resources = value["resources"]
    if not isinstance(resources, dict) or not resources:
        raise ValueError("Gazebo scenario resources are missing")
    packaged = Path(baseline["manifest"]).resolve().parent / "packaged"
    files = {}
    for relative, entry in resources.items():
        area, _, member = relative.partition("/")
        if area not in ("etc", "gazebo") or manifest["artifacts"][area].get(member) != entry:
            raise ValueError("Gazebo scenario resource differs from the build manifest")
        files[relative] = _read_file(packaged, relative, entry)
    plugins = {"gazebo/" + k for k in manifest["artifacts"]["gazebo"] if k.startswith("plugins/")}
    if (not plugins <= files.keys() or not {"gazebo/server.config", "gazebo/plugins/libGstCameraSystem.so",
            "gazebo/plugins/libMotorFailurePlugin.so"} <= files.keys()):
        raise ValueError("Gazebo scenario plugin/config closure is incomplete")
    # Include complete model directories (meshes, textures, configs), not just SDFs.
    for model in value["models"]:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", model):
            raise ValueError("Invalid Gazebo scenario model resource")
        required = {"gazebo/" + k for k in manifest["artifacts"]["gazebo"] if k.startswith(f"models/{model}/")}
        if not required or not required <= files.keys():
            raise ValueError("Gazebo scenario model resource closure is incomplete")
    world_file = f'gazebo/worlds/{value["world"]}.sdf'
    try:
        world = ET.fromstring(files[world_file]).find("world")
        if world is None or world.get("name") != value["world"]:
            raise ValueError("Gazebo scenario world identity differs")
        roots = [world]
        for model in value["models"]:
            root = ET.fromstring(files[f"gazebo/models/{model}/model.sdf"]).find("model")
            if root is None or root.get("name") != model:
                raise ValueError("Gazebo scenario model identity differs")
            roots.append(root)
        included = {node.findtext("uri", "").removeprefix("model://")
                    for root in roots for node in root.findall("include")}
        if set(value["models"]) != included | {value["model"]}:
            raise ValueError("Gazebo scenario model include closure differs")
        entities = [node.get("name") for node in world.findall("model")]
        entities += [node.findtext("name") or node.findtext("uri", "").removeprefix("model://")
                     for node in world.findall("include")]
        if sorted(entities) != sorted(value["scene_models"]):
            raise ValueError("Gazebo scenario scene declarations differ")
        expected = airframe_identity(value, files)
    except (KeyError, UnicodeError, ET.ParseError) as error:
        raise ValueError("Gazebo scenario resource closure is invalid") from error
    camera = value["camera"]
    if (not isinstance(camera, dict) or set(camera) != {"link", "sensor", "udp_port", "model"}
            or any(not isinstance(camera[k], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", camera[k])
                   for k in ("link", "sensor", "model")) or camera["model"] not in value["models"]
            or type(camera["udp_port"]) is not int or camera["udp_port"] != 5600):
        raise ValueError("Invalid Gazebo scenario camera contract")
    camera_root = ET.fromstring(files[f'gazebo/models/{camera["model"]}/model.sdf'])
    sensors = camera_root.findall(f'./model/link[@name="{camera["link"]}"]/sensor[@name="{camera["sensor"]}"]')
    if len(sensors) != 1 or sensors[0].get("type") != "camera":
        raise ValueError("Gazebo scenario camera is missing or ambiguous")
    return {"name": name, "descriptor_sha256": hashlib.sha256(raw).hexdigest(), "descriptor": value,
            "expected_parameters": expected, "build_manifest_sha256": baseline["manifest_sha256"]}


def scenario_environment(scenario: dict) -> dict[str, str]:
    descriptor = scenario["descriptor"]
    return {"PX4_GZ_MODEL_POSE": ",".join(str(n) for n in descriptor["spawn_pose"]),
            "PX4_VIDEO_HOST_IP": "127.0.0.1"}
