"""Explicit runtime scenarios over an unchanged, independently verified Gazebo build.

Repository descriptors select packaged resources and explicit pinned scene additions.
They never redefine build authority, modify an airframe, publish a scene command,
or qualify rendering/flight response.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import struct
import xml.etree.ElementTree as ET

SCENARIOS = Path(__file__).resolve().parents[1] / "native/gazebo/scenarios"


def _finite_vector(value, count):
    return (isinstance(value, list) and len(value) == count
            and all(type(v) in (int, float) and math.isfinite(v) for v in value))


def _canonical(node):
    return ET.canonicalize(ET.tostring(node, encoding="unicode"), strip_text=True)


def fixed_camera_optical_to_body(mount):
    """SDF camera +X/left/up mounting → optical right/down/forward → physical FRD."""
    from classes.aircraft_state import Quaternion

    if (not isinstance(mount, dict) or set(mount) != {"frame", "pose"}
            or mount["frame"] != "base_link_flu" or not _finite_vector(mount["pose"], 6)):
        raise ValueError("Gazebo fixed camera requires a finite base_link_flu mount pose")
    flu_to_frd = Quaternion(0., 1., 0., 0.)
    optical_to_camera_flu = Quaternion(.5, -.5, .5, -.5)
    camera_to_base_flu = Quaternion.from_euler(*mount["pose"][3:])
    return flu_to_frd.compose(camera_to_base_flu).compose(optical_to_camera_flu)


def _added_camera_model(value: dict, manifest: dict, files: dict) -> dict:
    """One fixed camera wrapper; the stock aircraft and camera remain byte-exact."""
    mount, declared = value["camera_mount"], value["added_model"]
    fixed_camera_optical_to_body(mount)
    if not {"etc/init.d-posix/rcS", "etc/init.d-posix/px4-rc.gzsim"} <= files.keys():
        raise ValueError("Gazebo composite requires its pinned autostart and model-spawn scripts")
    if (not isinstance(declared, dict) or set(declared) != {"model.sdf", "model.config"}
            or value["base_model"] == value["model"] or value["base_model"] not in value["models"]
            or value["camera"]["model"] in (value["base_model"], value["model"])):
        raise ValueError("Gazebo camera wrapper requires a declared stock base and fixed mount")
    additions = {}
    for name, pin in declared.items():
        relative = f'models/{value["model"]}/{name}'
        if relative in manifest["artifacts"]["gazebo"] or not isinstance(pin, dict) or pin.get("executable") is not False:
            raise ValueError("Gazebo camera wrapper must not replace packaged resources")
        files["gazebo/" + relative] = _read_file(SCENARIOS.parent, relative, pin)
        additions[relative] = pin
    pose = " ".join(str(n) for n in mount["pose"])
    articulated = value.get('articulated_camera') is not None
    child = 'cgo3_mount_link' if articulated else value['camera']['link']
    expected = ET.fromstring(f'''<sdf version="1.10"><model name="{value['model']}">
      <include merge="true"><uri>model://{value['base_model']}</uri></include>
      <include merge="true"><uri>model://{value['camera']['model']}</uri>
        <pose relative_to="base_link">{pose}</pose></include>
      <joint name="CameraJoint" type="fixed"><parent>base_link</parent><child>{child}</child>
        <pose relative_to="base_link">{pose}</pose></joint>
    </model></sdf>''')
    if articulated:
        from tools.gazebo_gimbal_resources import joint_pose_publisher, joint_state_publisher
        expected.find('model').extend((joint_pose_publisher(), joint_state_publisher()))
    try:
        actual = ET.fromstring(files[f'gazebo/models/{value["model"]}/model.sdf'])
        config = ET.fromstring(files[f'gazebo/models/{value["model"]}/model.config'])
        if (_canonical(actual) != _canonical(expected) or config.tag != "model"
                or config.findtext("name") != value["model"] or len(config.findall("sdf")) != 1
                or config.findtext("sdf") != "model.sdf" or config.find("sdf").get("version") != "1.10"):
            raise ValueError("Gazebo wrapper must contain only its stock includes and fixed camera joint")
    except ET.ParseError as error:
        raise ValueError("Gazebo camera wrapper is malformed") from error
    return additions


def _articulated_camera(value, manifest, files):
    from tools.gazebo_gimbal_resources import derive_joint_gimbal
    declaration = value['articulated_camera']
    if (not isinstance(declaration, dict) or set(declaration) != {
            'base_model', 'optics_model', 'mechanics', 'rate_deg_s', 'mass_scale', 'limits_rad', 'files'}
            or declaration['base_model'] != 'gimbal' or declaration['optics_model'] != 'mono_cam'
            or declaration['mechanics'] != 'ideal_joint_velocity'
            or set(declaration['files']) != {'model.sdf', 'model.config'}):
        raise ValueError('Gazebo articulated camera declaration invalid')
    name = value['camera']['model']
    expected, geometry = derive_joint_gimbal(files['gazebo/models/gimbal/model.sdf'],
        files['gazebo/models/mono_cam/model.sdf'], name=name, rate_deg_s=declaration['rate_deg_s'],
        mass_scale=declaration['mass_scale'], limits_rad=declaration['limits_rad'])
    additions = {}
    for member, pin in declaration['files'].items():
        relative = f'models/{name}/{member}'
        if relative in manifest['artifacts']['gazebo'] or pin.get('executable') is not False:
            raise ValueError('Gazebo articulated camera cannot replace packaged resources')
        raw = _read_file(SCENARIOS.parent, relative, pin)
        if member == 'model.sdf' and _canonical(ET.fromstring(raw)) != _canonical(ET.fromstring(expected)):
            raise ValueError('Gazebo articulated camera differs from declared stock derivative')
        if member == 'model.config':
            config = ET.fromstring(raw)
            if config.findtext('name') != name or [n.text for n in config.findall('sdf')] != ['model.sdf']:
                raise ValueError('Gazebo articulated camera model configuration invalid')
        additions[relative] = pin
        files['gazebo/' + relative] = raw
    return additions, geometry


def _raw_camera_server(value, files):
    """Remove only the redundant encoder; every simulation plugin stays identical."""
    pin = value['server_config']
    if not isinstance(pin, dict) or set(pin) != {'sha256', 'executable'} or pin['executable'] is not False:
        raise ValueError('Gazebo raw camera server config requires a nonexecutable hash pin')
    raw = _read_file(SCENARIOS.parent, 'server.config', pin)
    try:
        original = ET.fromstring(files['gazebo/server.config'])
        selected = ET.fromstring(raw)
        plugins = original.find('plugins')
        matches = [item for item in plugins if item.attrib == {
            'entity_name': '*', 'entity_type': 'world', 'filename': 'libGstCameraSystem.so',
            'name': 'custom::GstCameraSystem'} and len(item) == 0]
        if len(matches) != 1:
            raise ValueError('Gazebo stock encoder plugin is absent or ambiguous')
        plugins.remove(matches[0])
        if _canonical(selected) != _canonical(original):
            raise ValueError('Gazebo raw camera config may remove only the stock encoder')
    except (ET.ParseError, TypeError) as error:
        raise ValueError('Gazebo raw camera server config is malformed') from error
    return {'server.config': pin}


def _remove_static_scene_additions(world, declarations, files):
    if not isinstance(declarations, list) or not declarations:
        raise ValueError("Gazebo populated world requires declared static additions")
    names = set()
    for item in declarations:
        if (not isinstance(item, dict) or set(item) != {"name", "pose"}
                or not isinstance(item["name"], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", item["name"])
                or item["name"] in names or not _finite_vector(item["pose"], 6)):
            raise ValueError("Gazebo scene addition requires a unique name and finite ENU pose")
        names.add(item["name"])
        matches = [m for m in world.findall("model") if m.get("name") == item["name"]]
        if len(matches) != 1:
            raise ValueError("Gazebo static scene addition is missing or duplicated")
        model = matches[0]
        if (model.findtext("static") != "true" or model.find("pose") is None or model.find("pose").attrib
                or [float(n) for n in model.findtext("pose", "").split()] != item["pose"]
                or any(model.findall(".//" + tag) for tag in ("plugin", "sensor", "include", "collision", "joint", "model"))):
            raise ValueError("Gazebo scene additions must be static visual-only props")
        references = model.findall('.//uri')
        for tag in ('albedo_map', 'normal_map', 'roughness_map', 'metalness_map', 'emissive_map', 'environment_map', 'light_map'):
            references.extend(model.findall('.//' + tag))
        for uri in references:
            member = uri.text or ""
            if not member.startswith("model://") or "gazebo/models/" + member[8:] not in files:
                raise ValueError("Gazebo scene mesh must be a pinned local model resource")
        world.remove(model)


def _added_world(value: dict, manifest: dict, files: dict) -> dict:
    """Permit one additional world, never an override of a packaged resource."""
    addition = value["added_world"]
    if (not isinstance(addition, dict) or set(addition) != {"resource", "base_resource", "sha256", "executable"}
            or addition["resource"] != f'worlds/{value["world"]}.sdf'
            or not isinstance(addition["base_resource"], str)
            or not re.fullmatch(r"worlds/[a-z][a-z0-9_]*\.sdf", addition["base_resource"])
            or addition["resource"] in manifest["artifacts"]["gazebo"]
            or "gazebo/" + addition["base_resource"] not in files
            or addition["executable"] is not False):
        raise ValueError("Gazebo scenario must add one declared world without replacing packaged resources")
    pin = {k: addition[k] for k in ("sha256", "executable")}
    raw = _read_file(SCENARIOS.parent, addition["resource"], pin)
    target = value["target"]
    if (not isinstance(target, dict) or set(target) != {"name", "frame", "pose", "panel_size_m", "aim_point_m"}
            or not isinstance(target["name"], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", target["name"])
            or target["frame"] != "gazebo_world_enu"
            or not _finite_vector(target["pose"], 6) or target["pose"][3:] != [0, 0, 0]
            or not _finite_vector(target["panel_size_m"], 2) or min(target["panel_size_m"]) <= 0
            or not _finite_vector(target["aim_point_m"], 3) or target["aim_point_m"] != target["pose"][:3]):
        raise ValueError("Gazebo scenario target requires a finite static ENU vertical-panel contract")
    try:
        document = ET.fromstring(raw)
        worlds = document.findall("world")
        if len(worlds) != 1 or worlds[0].get("name") != value["world"]:
            raise ValueError("Gazebo added world identity differs")
        world = worlds[0]
        targets = [model for model in world.findall("model") if model.get("name") == target["name"]]
        if len(targets) != 1:
            raise ValueError("Gazebo scenario target is missing or duplicated")
        model = targets[0]
        pose = [float(n) for n in model.findtext("pose", "").split()]
        panel = model.findall('./link/visual[@name="panel"]/geometry/box/size')
        size = [float(n) for n in (panel[0].text or "").split()] if len(panel) == 1 else []
        if (model.findtext("static") != "true" or model.find("pose") is None or model.find("pose").attrib
                or pose != target["pose"]
                or not _finite_vector(size, 3) or min(size) <= 0 or size[1:] != target["panel_size_m"]
                or any(model.findall(".//" + kind) for kind in ("plugin", "sensor", "include", "uri", "collision"))):
            raise ValueError("Gazebo target must match its static visual-only panel declaration")
        world.remove(model)
        if value["schema_version"] >= 3:
            _remove_static_scene_additions(world, value["scene_additions"], files)
        base = ET.fromstring(files["gazebo/" + addition["base_resource"]]).find("world")
        if base is None:
            raise ValueError("Gazebo base world is missing")
        world.set("name", base.get("name", ""))
        if _canonical(world) != _canonical(base):
            raise ValueError("Gazebo added world changes more than its declared target and name")
    except (ET.ParseError, TypeError) as error:
        raise ValueError("Gazebo added world is malformed") from error
    files["gazebo/" + addition["resource"]] = raw
    return {addition["resource"]: pin}


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


def _scene_assets(value, files):
    """Explicit bounded PNG art assets, never executable/plugin/model overrides."""
    assets = value.get('scene_assets', {})
    if not isinstance(assets, dict):
        raise ValueError('Gazebo scene assets must be a pinned texture mapping')
    for relative, pin in assets.items():
        if (not isinstance(relative, str) or not re.fullmatch(
                r'models/pixeagle_training_art/materials/textures/[a-z0-9_-]+\.png', relative)
                or not isinstance(pin, dict) or pin.get('executable') is not False):
            raise ValueError('Gazebo scene asset role is limited to nonexecutable local PNG textures')
        raw = _read_file(SCENARIOS.parent, relative, pin)
        if (len(raw) < 24 or len(raw) > 4 * 1024 * 1024 or raw[:8] != b'\x89PNG\r\n\x1a\n'
                or raw[12:16] != b'IHDR' or any(not 1 <= n <= 4096 for n in struct.unpack('>II', raw[16:24]))):
            raise ValueError('Gazebo scene asset is not a bounded PNG texture')
        files['gazebo/' + relative] = raw
    return assets


def airframe_identity(scenario: dict, files: dict[str, bytes]) -> dict:
    """Read a pinned literal include chain; never execute shell or infer computed values."""
    chain = scenario["airframe_chain"]
    base_model = scenario.get("base_model", scenario["model"])
    first = f'etc/init.d-posix/airframes/{scenario["airframe_id"]}_gz_{base_model}'
    if not chain or chain[0] != first or len(set(chain)) != len(chain):
        raise ValueError("Gazebo scenario airframe chain differs from its model/ID")
    visited, expected, assignments = [], {"SYS_AUTOSTART": scenario["airframe_id"]}, set()

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
                    if depth or key == "SYS_AUTOSTART" or (name, key) in assignments or value is None:
                        raise ValueError(f"Gazebo scenario identity is ambiguous: {key}")
                    # PX4 airframes may override literal defaults from their
                    # included family defaults. Same-file duplicates still refuse.
                    assignments.add((name, key))
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
    if isinstance(value, dict) and value.get("schema_version") in (2, 3, 5):
        fields |= {"added_world", "target"}
    if isinstance(value, dict) and value.get("schema_version") in (3, 5):
        fields |= {"base_model", "added_model", "scene_additions", "camera_mount"}
        if "server_config" in value:
            fields.add("server_config")
        if value['schema_version'] == 5:
            fields.add('articulated_camera')
            if 'scene_assets' in value:
                fields.add('scene_assets')
    if (not isinstance(value, dict) or set(value) != fields or type(value["schema_version"]) is not int
            or value["schema_version"] not in (1, 2, 3, 5) or value["name"] != name):
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
            for key in (("model", "world", "base_model") if value["schema_version"] in (3, 5) else ("model", "world"))) or type(value["airframe_id"]) is not int
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
    camera = value["camera"]
    if (not isinstance(camera, dict) or set(camera) != {"link", "sensor", "udp_port", "model"}
            or any(not isinstance(camera[k], str) or not re.fullmatch(r"[a-z][a-z0-9_]*", camera[k])
                   for k in ("link", "sensor", "model")) or camera["model"] not in value["models"]
            or type(camera["udp_port"]) is not int or camera["udp_port"] != 5600):
        raise ValueError("Invalid Gazebo scenario camera contract")
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
    geometry = None
    additions = {}
    if value['schema_version'] == 5:
        additions, geometry = _articulated_camera(value, manifest, files)
    if value['schema_version'] in (3, 5):
        additions.update(_added_camera_model(value, manifest, files))
    if value['schema_version'] == 5:
        additions.update(_scene_assets(value, files))
    if "server_config" in value:
        additions.update(_raw_camera_server(value, files))
    # Include complete model directories (meshes, textures, configs), not just SDFs.
    for model in value["models"]:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", model):
            raise ValueError("Invalid Gazebo scenario model resource")
        required = {"gazebo/" + k for k in {**manifest["artifacts"]["gazebo"], **additions}
                    if k.startswith(f"models/{model}/")}
        if not required or not required <= files.keys():
            raise ValueError("Gazebo scenario model resource closure is incomplete")
    if value["schema_version"] in (2, 3, 5):
        additions.update(_added_world(value, manifest, files))
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
    camera_root = ET.fromstring(files[f'gazebo/models/{camera["model"]}/model.sdf'])
    sensors = camera_root.findall(f'./model/link[@name="{camera["link"]}"]/sensor[@name="{camera["sensor"]}"]')
    if len(sensors) != 1 or sensors[0].get("type") != ('rgbd_camera' if geometry else 'camera'):
        raise ValueError("Gazebo scenario camera is missing or ambiguous")
    return {"name": name, "descriptor_sha256": hashlib.sha256(raw).hexdigest(), "descriptor": value,
            "expected_parameters": expected, "build_manifest_sha256": baseline["manifest_sha256"],
            **({'articulated_geometry': geometry} if geometry is not None else {}),
            **({"added_resources": additions} if additions else {})}


def stage_scenario_resources(scenario: dict, runtime: Path) -> list[str]:
    """Freeze verified additions in this private run; return read-only file mounts."""
    args = []
    for relative, pin in scenario.get("added_resources", {}).items():
        raw = _read_file(SCENARIOS.parent, relative, pin)
        destination = runtime / "scenario" / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with destination.open("xb") as stream:
            stream.write(raw)
        destination.chmod(0o444)
        args.extend(["--mount", f"type=bind,src={destination.resolve()},dst=/opt/px4/gazebo/{relative},readonly"])
    return args


def scenario_environment(scenario: dict) -> dict[str, str]:
    descriptor = scenario["descriptor"]
    return {"PX4_GZ_MODEL_POSE": ",".join(str(n) for n in descriptor["spawn_pose"]),
            "PX4_VIDEO_HOST_IP": "127.0.0.1",
            **({"PX4_SYS_AUTOSTART": str(descriptor["airframe_id"])} if descriptor["schema_version"] >= 3 else {})}
