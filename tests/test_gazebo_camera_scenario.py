"""Synthetic resource/scene contracts. These tests never launch Gazebo or render pixels."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import sys
import hashlib
import json
from pathlib import Path
import socket
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import pytest

from tools import gazebo_scenario as scenario
from tools import sih_isolated_host as host
from tools import run_native_vector_sih as runner

NAME = "x500-mono-camera-aruco-v1"
BOARD = "x500-mono-camera-board-v1"
QUADPLANE = "standard-vtol-mono-camera-courtyard-v1"


@pytest.fixture
def package(tmp_path, monkeypatch):
    value = json.loads((scenario.SCENARIOS / (NAME + ".json")).read_text())
    resources = {
        value["airframe_chain"][0]: '. ${R}etc/init.d-posix/airframes/4001_gz_x500\n',
        value["airframe_chain"][1]: '. ${R}etc/init.d/rc.mc_defaults\nparam set-default CA_AIRFRAME 0\n'
            'param set-default CA_ROTOR_COUNT 4\nparam set-default SIM_GZ_EN 1\n',
        value["airframe_chain"][2]: 'param set-default MAV_TYPE 2\n',
        'gazebo/worlds/aruco.sdf': '<sdf><world name="aruco"><model name="ground_plane"/>'
            '<include><uri>model://arucotag</uri></include></world></sdf>',
        'gazebo/models/x500_mono_cam/model.sdf': '<sdf><model name="x500_mono_cam">'
            '<include><uri>x500</uri></include><include><uri>model://mono_cam</uri></include></model></sdf>',
        'gazebo/models/x500/model.sdf': '<sdf><model name="x500"><include><uri>model://x500_base</uri>'
            '</include></model></sdf>',
        'gazebo/models/x500_base/model.sdf': '<sdf><model name="x500_base"/></sdf>',
        'gazebo/models/mono_cam/model.sdf': '<sdf><model name="mono_cam"><link name="camera_link">'
            '<sensor name="camera" type="camera"/></link></model></sdf>',
        'gazebo/models/arucotag/model.sdf': '<sdf><model name="arucotag"/></sdf>',
        'gazebo/models/arucotag/arucotag.png': 'synthetic texture bytes',
        'gazebo/server.config': 'synthetic server config',
        'gazebo/plugins/libGstCameraSystem.so': 'synthetic camera plugin',
        'gazebo/plugins/libMotorFailurePlugin.so': 'synthetic motor plugin',
    }
    manifest = {'kind': 'pixeagle_gazebo_build', 'image_id': value['image_id'],
        'build': {'model': 'quadtailsitter', 'world': 'default', 'airframe_id': 4018, 'distribution': 'harmonic'},
        'artifacts': {'binary_sha256': value['binary_sha256'], 'etc': {}, 'gazebo': {}}}
    baseline = {'kind': 'verified_gazebo_source_build', 'manifest': str(tmp_path / 'build.json'),
        'manifest_sha256': value['build_manifest_sha256'], 'image_id': value['image_id'],
        'binary_sha256': value['binary_sha256']}
    value['resources'] = {}
    for name, raw in resources.items():
        path = tmp_path / 'packaged' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw)
        pin = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'executable': False}
        value['resources'][name] = pin
        area, member = name.split('/', 1)
        manifest['artifacts'][area][member] = pin.copy()
    directory = tmp_path / 'scenarios'
    directory.mkdir()
    monkeypatch.setattr(scenario, 'SCENARIOS', directory)
    def save():
        (directory / (NAME + '.json')).write_text(json.dumps(value))
    save()
    return value, manifest, baseline, save


def test_explicit_scenario_preserves_build_identity_and_stages_no_control(tmp_path, package):
    value, manifest, baseline, _ = package
    before = deepcopy(manifest)
    checked = scenario.verified_scenario(NAME, baseline, manifest)
    assert checked['expected_parameters'] == {'SYS_AUTOSTART': 4010, 'MAV_TYPE': 2,
        'CA_AIRFRAME': 0, 'CA_ROTOR_COUNT': 4, 'SIM_GZ_EN': 1}
    argv = host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
        token='owner', name='camera', gazebo_scenario=NAME)
    assert 'PX4_SIM_MODEL=gz_x500_mono_cam' in argv and 'PX4_GZ_WORLD=aruco' in argv
    assert 'PX4_GZ_MODEL_POSE=-6,0,0,0,0,0' in argv
    assert 'PX4_VIDEO_HOST_IP=127.0.0.1' in argv
    assert baseline['image_id'] in argv and argv[argv.index('--network') + 1] == 'none'
    assert not {'arm', 'takeoff', '--privileged', '-p', '--device'} & set(argv)
    assert manifest == before and manifest['build']['airframe_id'] == 4018


def test_training_template_binds_new_verified_build_without_relabelling_history(tmp_path, package):
    value, manifest, baseline, save = package
    original = (scenario.SCENARIOS / (NAME + '.json')).read_bytes()
    baseline.update(image_id='sha256:'+'a'*64, binary_sha256='b'*64, manifest_sha256='c'*64)
    manifest.update(image_id=baseline['image_id'])
    manifest['artifacts']['binary_sha256'] = baseline['binary_sha256']
    plugin = tmp_path / 'packaged/gazebo/plugins/libGstCameraSystem.so'
    plugin.write_bytes(b'newly compiled verified plugin')
    manifest['artifacts']['gazebo']['plugins/libGstCameraSystem.so'] = {
        'sha256': hashlib.sha256(plugin.read_bytes()).hexdigest(), 'executable': False}
    with pytest.raises(ValueError, match='exact verified'):
        scenario.verified_scenario(NAME, baseline, manifest)
    checked = scenario.verified_scenario(NAME, baseline, manifest, bind_to_build=True)
    assert checked['descriptor']['image_id'] == baseline['image_id']
    assert checked['template_binding']['template_sha256'] == hashlib.sha256(original).hexdigest()
    assert 'gazebo/plugins/libGstCameraSystem.so' in checked['template_binding']['changed_resources']
    assert (scenario.SCENARIOS / (NAME + '.json')).read_bytes() == original
    assert value['resources']['gazebo/plugins/libGstCameraSystem.so']['sha256'] != hashlib.sha256(plugin.read_bytes()).hexdigest()
    argv = host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
        token='owner', name='camera', gazebo_scenario=NAME, bind_gazebo_template=True)
    assert baseline['image_id'] in argv and '--network' in argv


@pytest.mark.parametrize('fault', ['missing_resource', 'altered_bytes', 'bad_identity', 'bad_scene'])
def test_template_binding_retains_resource_scene_and_aircraft_validation(tmp_path, package, fault):
    value, manifest, baseline, save = package
    relative='gazebo/plugins/libGstCameraSystem.so'
    if fault == 'missing_resource': del manifest['artifacts']['gazebo']['plugins/libGstCameraSystem.so']
    elif fault == 'altered_bytes': (tmp_path / 'packaged' / relative).write_bytes(b'unmanifested change')
    elif fault == 'bad_identity': value['identity_parameters'].append('UNDECLARED_PARAMETER')
    else: value['scene_models'].append('hidden_object')
    save()
    with pytest.raises(ValueError):
        scenario.verified_scenario(NAME, baseline, manifest, bind_to_build=True)


@pytest.mark.parametrize('change', ['model', 'world', 'airframe', 'image', 'elf', 'manifest', 'variant',
    'missing_texture', 'missing_plugin', 'missing_airframe', 'resource_pin', 'resource_bytes', 'symlink',
    'nan', 'inf', 'bool_pose', 'short_pose', 'unknown', 'camera', 'extra_scene', 'schema', 'include',
    'cycle', 'conditional', 'duplicate_parameter', 'computed_parameter', 'missing_parameter'])
def test_bad_scenario_refuses_before_staging(tmp_path, package, change):
    value, manifest, baseline, save = package
    if change == 'model': value['model'] = 'x500'
    if change == 'world': value['world'] = 'default'
    if change == 'airframe': value['airframe_id'] = 4014
    if change in ('image', 'elf', 'manifest'):
        baseline[{'image': 'image_id', 'elf': 'binary_sha256', 'manifest': 'manifest_sha256'}[change]] = 'wrong'
    if change == 'variant': manifest['build']['resource_variant'] = {'name': 'quadtailsitter-no-pitot-v1'}
    if change.startswith('missing_') and change != 'missing_parameter':
        name = {'missing_texture': 'gazebo/models/arucotag/arucotag.png',
            'missing_plugin': 'gazebo/plugins/libGstCameraSystem.so',
            'missing_airframe': value['airframe_chain'][1]}[change]
        del value['resources'][name]
    name = value['airframe_chain'][1]
    path = tmp_path / 'packaged' / name
    if change == 'resource_pin': value['resources'][name]['sha256'] = '0' * 64
    if change == 'resource_bytes': path.write_text('changed')
    if change == 'symlink':
        moved = path.with_suffix('.copy'); path.rename(moved); path.symlink_to(moved)
    if change in ('nan', 'inf', 'bool_pose'): value['spawn_pose'][0] = {'nan': float('nan'), 'inf': float('inf'), 'bool_pose': True}[change]
    if change == 'short_pose': value['spawn_pose'].pop()
    if change == 'camera': value['camera']['sensor'] = 'missing'
    if change == 'extra_scene': value['scene_models'].append('other_aircraft')
    if change == 'schema': value['schema_version'] = True
    if change in ('include', 'cycle', 'conditional', 'duplicate_parameter', 'computed_parameter', 'missing_parameter'):
        text = path.read_text()
        if change == 'include': text += '. ${R}etc/undeclared\n'
        if change == 'cycle': text += '. ${R}' + value['airframe_chain'][0] + '\n'
        if change == 'conditional': text = 'if true; then\n' + text + 'fi\n'
        if change == 'duplicate_parameter': text += 'param set-default CA_ROTOR_COUNT 4\n'
        if change == 'computed_parameter': text = text.replace('CA_ROTOR_COUNT 4', 'CA_ROTOR_COUNT $COUNT')
        if change == 'missing_parameter': text = text.replace('param set-default CA_ROTOR_COUNT 4\n', '')
        path.write_text(text)
        pin = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'executable': False}
        value['resources'][name] = pin
        manifest['artifacts']['etc'][name.removeprefix('etc/')] = pin
    save()
    with pytest.raises(ValueError):
        host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
            token='owner', name='camera', gazebo_scenario='unknown-v1' if change == 'unknown' else NAME)
    assert not (tmp_path / 'run').exists()


@pytest.mark.parametrize('requested', ['sihsim_quadx', 'gz_quadtailsitter', 'gz_x500'])
def test_explicit_model_cannot_be_silently_replaced_by_camera_scenario(tmp_path, package, requested):
    _, manifest, baseline, _ = package
    with pytest.raises(ValueError, match='Requested simulator model differs'):
        host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
            token='owner', name='camera', gazebo_scenario=NAME, model=requested)
    assert not (tmp_path / 'run').exists()


def test_scenario_is_not_a_sih_or_unverified_build_escape(tmp_path):
    with pytest.raises(ValueError, match='verified Gazebo'):
        host.simulation_launch_args('sih', {}, None, runtime=tmp_path, token='x', name='x', gazebo_scenario=NAME)
    with pytest.raises(ValueError, match='verified Gazebo'):
        runner.verify_simulator('no-query', 0, tmp_path / 'absent', gazebo_scenario=NAME)


@pytest.mark.parametrize('parameter', ['SYS_AUTOSTART', 'MAV_TYPE', 'CA_ROTOR_COUNT'])
def test_startup_overlay_cannot_change_declared_aircraft_identity(tmp_path, package, parameter):
    _, manifest, baseline, _ = package
    with pytest.raises(ValueError, match='cannot override'):
        host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
            token='owner', name='camera', gazebo_scenario=NAME, startup_parameters={parameter: '1'})
    assert not (tmp_path / 'run').exists()


def board_package(package):
    value, manifest, baseline, _ = package
    root = Path(__file__).resolve().parents[1]
    declaration = json.loads((root / 'native/gazebo/scenarios' / (BOARD + '.json')).read_text())
    value.update({k: declaration[k] for k in ('schema_version', 'name', 'world', 'scene_models', 'added_world', 'target')})
    base = Path(baseline['manifest']).parent / 'packaged/gazebo/worlds/aruco.sdf'
    document = ET.fromstring(base.read_bytes());world = document.find('world');world.set('name', value['world'])
    source = ET.parse(root / 'native/gazebo/worlds/training_board_v1.sdf')
    world.append(next(model for model in source.findall('./world/model') if model.get('name') == 'training_board'))
    addition = scenario.SCENARIOS.parent / value['added_world']['resource']
    addition.parent.mkdir(parents=True);addition.write_bytes(ET.tostring(document))
    def save(*, repin=False):
        if repin:value['added_world']['sha256'] = hashlib.sha256(addition.read_bytes()).hexdigest()
        (scenario.SCENARIOS / (BOARD + '.json')).write_text(json.dumps(value))
    save(repin=True)
    return value, manifest, baseline, save, addition


def test_board_stages_only_declared_read_only_world_without_changing_build(tmp_path, package):
    value, manifest, baseline, _, addition = board_package(package)
    before = deepcopy(manifest)
    checked = scenario.verified_scenario(BOARD, baseline, manifest)
    argv = host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path/'run',
        token='owner', name='camera', gazebo_scenario=BOARD)
    staged = tmp_path / 'run/scenario/worlds/training_board_v1.sdf'
    assert staged.read_bytes() == addition.read_bytes()
    assert staged.stat().st_mode & 0o777 == 0o444
    assert f'type=bind,src={staged},dst=/opt/px4/gazebo/worlds/training_board_v1.sdf,readonly' in argv
    assert 'PX4_GZ_WORLD=training_board_v1' in argv
    assert checked['descriptor']['target']['aim_point_m'] == [12, 0, 6]
    assert checked['added_resources'] == {'worlds/training_board_v1.sdf': {
        'sha256': value['added_world']['sha256'], 'executable': False}}
    assert manifest == before and 'worlds/training_board_v1.sdf' not in manifest['artifacts']['gazebo']


@pytest.mark.parametrize('fault', [None, 'undeclared', 'collision', 'asset_hash', 'asset_executable'])
def test_fixed_camera_scene_reuses_bounded_props_and_textures(tmp_path, package, fault):
    value, manifest, baseline, save, world_path = board_package(package)
    before = deepcopy(manifest)
    root = Path(__file__).resolve().parents[1] / 'native/gazebo'
    coast = json.loads((root / 'scenarios/quadtailsitter-gimbal-training-coast-v1.json').read_text())
    value['scene_assets'] = deepcopy(coast['scene_assets'])
    for relative in value['scene_assets']:
        path = scenario.SCENARIOS.parent / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((root / relative).read_bytes())
    value['scene_additions'] = [{'name': 'pixeagle_sign', 'pose': [20, 5, 3, 0, 0, 0]}]
    value['scene_models'].append('pixeagle_sign')
    document = ET.parse(world_path)
    sign = ET.fromstring('<model name="pixeagle_sign"><static>true</static><pose>20 5 3 0 0 0</pose>'
        '<link name="art"><visual name="sign"><geometry><plane><size>4 2</size></plane></geometry>'
        '<material><pbr><metal><albedo_map>model://pixeagle_training_art/materials/textures/'
        'pixeagle-banner.png</albedo_map></metal></pbr></material></visual></link></model>')
    document.find('world').append(sign)
    if fault == 'collision': ET.SubElement(sign.find('link'), 'collision', name='hidden')
    document.write(world_path)
    if fault == 'undeclared': value['scene_additions'][0]['name'] = 'missing_sign'
    if fault == 'asset_hash': next(iter(value['scene_assets'].values()))['sha256'] = '0' * 64
    if fault == 'asset_executable': next(iter(value['scene_assets'].values()))['executable'] = True
    save(repin=True)
    if fault:
        with pytest.raises(ValueError):
            scenario.verified_scenario(BOARD, baseline, manifest)
    else:
        checked = scenario.verified_scenario(BOARD, baseline, manifest)
        assert checked['expected_parameters']['MAV_TYPE'] == 2
        assert checked['descriptor']['camera'] == value['camera']
        assert set(checked['added_resources']) == {value['added_world']['resource'], *value['scene_assets']}
    assert manifest == before


def test_mc_coast_keeps_stock_aircraft_and_same_shared_world(tmp_path, monkeypatch):
    from tools import build_gazebo_training_world as builder
    root = Path(__file__).resolve().parents[1] / 'native/gazebo/scenarios'
    base = json.loads((root / 'x500-mono-camera-board-v3.json').read_text())
    coast = json.loads((root / 'quadtailsitter-gimbal-training-coast-v2.json').read_text())
    current = json.loads((root / 'x500-mono-camera-training-coast-v2.json').read_text())
    for key in ('model', 'camera', 'airframe_id', 'airframe_chain', 'identity_parameters', 'spawn_pose'):
        assert current[key] == base[key]
    for key in ('world', 'scene_models', 'added_world', 'target', 'scene_additions', 'scene_assets'):
        assert current[key] == coast[key]
    assert 'articulated_camera' not in current and len(current['scene_additions']) > 34
    (tmp_path / 'scenarios').mkdir()
    original = (root / 'x500-mono-camera-board-v3.json').read_bytes()
    (tmp_path / 'scenarios/x500-mono-camera-board-v3.json').write_bytes(original)
    world = tmp_path / coast['added_world']['resource']
    world.parent.mkdir()
    world.write_bytes((root.parent / coast['added_world']['resource']).read_bytes())
    monkeypatch.setattr(builder, 'RESOURCE', tmp_path)
    assert builder.fixed_camera_scene('x500-mono-camera-board-v3', coast, current['name']) == current
    assert (tmp_path / 'scenarios/x500-mono-camera-board-v3.json').read_bytes() == original


@pytest.mark.parametrize('change', ['hash', 'executable', 'file_mode', 'replace_packaged', 'traversal', 'symlink',
    'missing', 'extra_declaration', 'target_frame', 'target_nan', 'target_bool', 'target_size', 'target_aim',
    'target_rotated', 'target_pose', 'target_plugin', 'target_sensor', 'target_collision', 'target_dynamic',
    'target_missing', 'target_duplicate', 'panel_size', 'world_gravity', 'world_extra_model', 'world_plugin'])
def test_added_world_cannot_hide_physics_resource_or_target_changes(tmp_path, package, change):
    value, manifest, baseline, save, addition = board_package(package)
    if change == 'hash':value['added_world']['sha256'] = '0'*64
    if change == 'executable':value['added_world']['executable'] = True
    if change == 'file_mode':addition.chmod(0o755)
    if change == 'replace_packaged':value['added_world']['resource'] = 'worlds/aruco.sdf'
    if change == 'traversal':value['added_world']['resource'] = '../other.sdf'
    if change == 'symlink':
        renamed = addition.with_suffix('.copy');addition.rename(renamed);addition.symlink_to(renamed)
    if change == 'missing':addition.unlink()
    if change == 'extra_declaration':value['added_world']['other'] = 'unexpected'
    if change == 'target_frame':value['target']['frame'] = 'ned'
    if change == 'target_nan':value['target']['pose'][0] = float('nan')
    if change == 'target_bool':value['target']['panel_size_m'][0] = True
    if change == 'target_size':value['target']['panel_size_m'][0] = -1
    if change == 'target_aim':value['target']['aim_point_m'][2] = 7
    if change == 'target_rotated':value['target']['pose'][5] = 1
    xml_changes = {'target_pose', 'target_plugin', 'target_sensor', 'target_collision', 'target_dynamic',
                   'target_missing', 'target_duplicate', 'panel_size', 'world_gravity', 'world_extra_model', 'world_plugin'}
    if change in xml_changes:
        doc = ET.parse(addition);world = doc.find('world')
        model = next(m for m in world.findall('model') if m.get('name') == 'training_board')
        if change == 'target_pose':model.find('pose').text = '12 0 8 0 0 0'
        if change in ('target_plugin', 'target_sensor', 'target_collision'):ET.SubElement(model, change.removeprefix('target_'))
        if change == 'target_dynamic':model.find('static').text = 'false'
        if change == 'target_missing':world.remove(model)
        if change == 'target_duplicate':world.append(deepcopy(model))
        if change == 'panel_size':model.find('./link/visual[@name="panel"]/geometry/box/size').text = '0.1 8 6'
        if change == 'world_gravity':ET.SubElement(world, 'gravity').text = '0 0 -4'
        if change == 'world_extra_model':ET.SubElement(world, 'model', {'name': 'hidden'})
        if change == 'world_plugin':ET.SubElement(world, 'plugin', {'name': 'hidden'})
        doc.write(addition)
    save(repin=change in xml_changes)
    with pytest.raises(ValueError):
        host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path/'run',
            token='owner', name='camera', gazebo_scenario=BOARD)
    assert not (tmp_path/'run').exists()


def test_added_resource_is_rechecked_before_private_staging(tmp_path, package):
    _, manifest, baseline, _, addition = board_package(package)
    checked = scenario.verified_scenario(BOARD, baseline, manifest)
    addition.write_text('changed after descriptor validation')
    with pytest.raises(ValueError, match='resource changed'):
        scenario.stage_scenario_resources(checked, tmp_path/'run')
    assert not (tmp_path/'run').exists()


def quadplane_package(package, scenario_name=QUADPLANE):
    value, manifest, baseline, _ = package
    root = Path(__file__).resolve().parents[1] / 'native/gazebo'
    declaration = json.loads((root / 'scenarios' / (scenario_name + '.json')).read_text())
    value.clear()
    value.update(declaration)
    baseline.update(image_id=value['image_id'], binary_sha256=value['binary_sha256'],
                    manifest_sha256=value['build_manifest_sha256'])
    manifest['image_id'] = value['image_id']
    manifest['artifacts']['binary_sha256'] = value['binary_sha256']
    packaged = Path(baseline['manifest']).parent / 'packaged'
    extra = {
        value['airframe_chain'][0]: '. ${R}etc/init.d/rc.vtol_defaults\nparam set-default SIM_GZ_EN 1\n'
            'param set-default CA_AIRFRAME 2\nparam set-default CA_ROTOR_COUNT 5\n'
            'param set-default CA_SV_CS_COUNT 3\nparam set-default VT_TYPE 2\n',
        value['airframe_chain'][1]: 'param set-default MAV_TYPE 22\n',
        'etc/init.d-posix/rcS': 'synthetic reviewed autostart fixture',
        'etc/init.d-posix/px4-rc.gzsim': 'synthetic reviewed spawn fixture',
        'gazebo/models/standard_vtol/model.sdf': '<sdf><model name="standard_vtol"/></sdf>',
        'gazebo/models/rover_ackermann/meshes/rover_ackermann_base.dae': 'synthetic local mesh',
    }
    if value['base_model'] == 'quadtailsitter':
        extra[value['airframe_chain'][0]] = ('. ${R}etc/init.d/rc.vtol_defaults\nparam set-default MAV_TYPE 20\n'
            'param set-default SIM_GZ_EN 1\nparam set-default CA_AIRFRAME 4\nparam set-default CA_ROTOR_COUNT 4\n'
            'param set-default CA_SV_CS_COUNT 0\nparam set-default VT_TYPE 0\n')
        del extra['gazebo/models/standard_vtol/model.sdf']
        extra['gazebo/models/quadtailsitter/model.sdf'] = ('<sdf><model name="quadtailsitter">'
            '<include><uri>model://airspeed</uri></include></model></sdf>')
        extra['gazebo/models/airspeed/model.sdf'] = '<sdf><model name="airspeed"/></sdf>'
    if 'server_config' in value:
        raw = (root / 'server.config').read_bytes()
        server = ET.fromstring(raw)
        ET.SubElement(server.find('plugins'), 'plugin', dict(entity_name='*', entity_type='world',
            filename='libGstCameraSystem.so', name='custom::GstCameraSystem'))
        extra['gazebo/server.config'] = ET.tostring(server).decode()
        (scenario.SCENARIOS.parent / 'server.config').write_bytes(raw)
    for relative, raw in extra.items():
        path = packaged / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw)
        area, member = relative.split('/', 1)
        manifest['artifacts'][area][member] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'executable': False}
    members = {*extra, 'gazebo/worlds/aruco.sdf', 'gazebo/server.config'}
    members.update('gazebo/' + name for name in manifest['artifacts']['gazebo']
                   if name.startswith(('models/mono_cam/', 'models/arucotag/', 'plugins/')))
    value['resources'] = {name: manifest['artifacts'][name.split('/', 1)[0]][name.split('/', 1)[1]] for name in members}
    document = ET.parse(packaged / 'gazebo/worlds/aruco.sdf')
    world = document.find('world')
    world.set('name', value['world'])
    actual = ET.parse(root / value['added_world']['resource'])
    names = {value['target']['name'], *(item['name'] for item in value['scene_additions'])}
    for model in actual.findall('./world/model'):
        if model.get('name') in names:
            world.append(deepcopy(model))
    added = {}
    for name in value['added_model']:
        relative = f'models/{value["model"]}/{name}'
        path = scenario.SCENARIOS.parent / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((root / relative).read_bytes())
        added[relative] = path
    world_path = scenario.SCENARIOS.parent / value['added_world']['resource']
    world_path.parent.mkdir(parents=True, exist_ok=True)
    document.write(world_path)
    added[value['added_world']['resource']] = world_path
    def save(*, repin=False):
        if repin:
            value['added_world']['sha256'] = hashlib.sha256(world_path.read_bytes()).hexdigest()
            for name in value['added_model']:
                value['added_model'][name]['sha256'] = hashlib.sha256(added[f'models/{value["model"]}/{name}'].read_bytes()).hexdigest()
        (scenario.SCENARIOS / (scenario_name + '.json')).write_text(json.dumps(value))
    save(repin=True)
    return value, manifest, baseline, save, added


def test_quadplane_uses_stock_airframe_and_exact_camera_only_additions(tmp_path, package):
    value, manifest, baseline, _, added = quadplane_package(package)
    before = deepcopy(manifest)
    checked = scenario.verified_scenario(QUADPLANE, baseline, manifest)
    assert checked['expected_parameters'] == {'SYS_AUTOSTART': 4004, 'MAV_TYPE': 22,
        'CA_AIRFRAME': 2, 'CA_ROTOR_COUNT': 5, 'CA_SV_CS_COUNT': 3, 'VT_TYPE': 2, 'SIM_GZ_EN': 1}
    argv = host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
        token='owner', name='quadplane', gazebo_scenario=QUADPLANE)
    assert 'PX4_SYS_AUTOSTART=4004' in argv and 'PX4_SIM_MODEL=gz_standard_vtol_mono_cam' in argv
    assert 'PX4_GZ_WORLD=training_courtyard_v1' in argv
    assert set(checked['added_resources']) == set(added) and manifest == before
    for relative, original in added.items():
        staged = tmp_path / 'run/scenario' / relative
        assert staged.read_bytes() == original.read_bytes() and staged.stat().st_mode & 0o777 == 0o444
        assert f'type=bind,src={staged},dst=/opt/px4/gazebo/{relative},readonly' in argv


@pytest.mark.parametrize('change', ['base_model', 'airframe', 'missing_rcs', 'missing_mesh', 'extra_file',
    'model_hash', 'model_executable', 'model_symlink', 'model_missing', 'camera_frame', 'camera_nan',
    'camera_rotation', 'joint_type', 'joint_child', 'joint_pose', 'camera_uri', 'base_uri', 'aircraft_override',
    'wrapper_plugin', 'model_config', 'scene_duplicate', 'scene_pose', 'scene_nan', 'scene_dynamic',
    'scene_plugin', 'scene_collision', 'scene_remote_uri', 'scene_undeclared_uri', 'scene_frame', 'world_extra'])
def test_quadplane_cannot_hide_aircraft_camera_or_world_changes(tmp_path, package, change):
    value, manifest, baseline, save, added = quadplane_package(package)
    wrapper = added[f'models/{value["model"]}/model.sdf']
    world_path = added[value['added_world']['resource']]
    repin = False
    if change == 'base_model': value['base_model'] = 'quadtailsitter'
    if change == 'airframe': value['airframe_id'] = 4018
    if change == 'missing_rcs': del value['resources']['etc/init.d-posix/rcS']
    if change == 'missing_mesh': del value['resources']['gazebo/models/rover_ackermann/meshes/rover_ackermann_base.dae']
    if change == 'extra_file': value['added_model']['other.sdf'] = value['added_model']['model.sdf']
    if change == 'model_hash': value['added_model']['model.sdf']['sha256'] = '0' * 64
    if change == 'model_executable': wrapper.chmod(0o755)
    if change == 'model_symlink':
        target = wrapper.with_suffix('.copy'); wrapper.rename(target); wrapper.symlink_to(target)
    if change == 'model_missing': wrapper.unlink()
    if change == 'camera_frame': value['camera_mount']['frame'] = 'optical'
    if change == 'camera_nan': value['camera_mount']['pose'][0] = float('nan')
    if change == 'camera_rotation': value['camera_mount']['pose'][4] = 1
    if change in ('joint_type', 'joint_child', 'joint_pose', 'camera_uri', 'base_uri', 'aircraft_override', 'wrapper_plugin'):
        doc = ET.parse(wrapper); model = doc.find('model'); joint = model.find('joint'); includes = model.findall('include')
        if change == 'joint_type': joint.set('type', 'revolute')
        if change == 'joint_child': joint.find('child').text = 'wrong_link'
        if change == 'joint_pose': joint.find('pose').text = '1 0 0 0 0 0'
        if change == 'camera_uri': includes[1].find('uri').text = 'model://gimbal'
        if change == 'base_uri': includes[0].find('uri').text = 'model://quadtailsitter'
        if change == 'aircraft_override': ET.SubElement(model, 'link', {'name': 'base_link'})
        if change == 'wrapper_plugin': ET.SubElement(model, 'plugin', {'name': 'hidden'})
        doc.write(wrapper); repin = True
    if change == 'model_config':
        added[f'models/{value["model"]}/model.config'].write_text('<model><name>wrong</name><sdf>other.sdf</sdf></model>')
        repin = True
    if change == 'scene_duplicate': value['scene_additions'].append(value['scene_additions'][0])
    if change == 'scene_pose': value['scene_additions'][0]['pose'][2] += 1
    if change == 'scene_nan': value['scene_additions'][0]['pose'][0] = float('nan')
    if change in ('scene_dynamic', 'scene_plugin', 'scene_collision', 'scene_remote_uri', 'scene_undeclared_uri', 'scene_frame', 'world_extra'):
        doc = ET.parse(world_path); world = doc.find('world')
        model = next(m for m in world.findall('model') if m.get('name') == 'parked_car_north')
        if change == 'scene_dynamic': model.find('static').text = 'false'
        if change == 'scene_frame': model.find('pose').set('relative_to', 'warehouse_north')
        if change in ('scene_plugin', 'scene_collision'): ET.SubElement(model, change.removeprefix('scene_'))
        if change == 'scene_remote_uri': model.find('.//uri').text = 'https://fuel.gazebosim.org/not-pinned'
        if change == 'scene_undeclared_uri': model.find('.//uri').text = 'model://unlisted/car.dae'
        if change == 'world_extra': ET.SubElement(world, 'model', {'name': 'hidden'})
        doc.write(world_path); repin = True
    save(repin=repin)
    with pytest.raises(ValueError):
        host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path / 'run',
            token='owner', name='quadplane', gazebo_scenario=QUADPLANE)
    assert not (tmp_path / 'run').exists()


RUNTIME_CHANGES = [None, 'model', 'world', 'image', 'binary', 'spawn', 'camera_host',
    'runtime_resources', 'runtime_parent_airframe', 'extra_entity', 'missing_marker', 'extra_topic_model',
    'missing_image', 'extra_image', 'parameter', 'empty_partition']


@pytest.mark.parametrize('board,change', [(board, change) for board in (False, True, 'quadplane') for change in RUNTIME_CHANGES]
    + [(board, change) for board in (True, 'quadplane') for change in ('world_bytes', 'missing_world_file', 'writable_world', 'missing_world_mount')]
    + [('quadplane', change) for change in ('autostart', 'wrapper_bytes', 'missing_wrapper_mount')])
def test_runtime_requires_actual_scenario_and_keeps_original_build(tmp_path, package, monkeypatch, board, change):
    if board == 'quadplane':
        value, manifest, baseline, _, _ = quadplane_package(package)
    elif board:
        value, manifest, baseline, _, _ = board_package(package)
    else:
        value, manifest, baseline, _ = package
    checked_scenario = scenario.verified_scenario(value['name'], baseline, manifest)
    expected_params = checked_scenario['expected_parameters']
    monkeypatch.setattr(runner, 'verified_simulation_build', lambda *a, **k: ('gazebo', baseline, manifest))
    environment = {'PX4_GZ_WORLD': value['world'], 'PX4_GZ_MODELS': '/opt/px4/gazebo/models',
        'PX4_GZ_WORLDS': '/opt/px4/gazebo/worlds',
        'GZ_SIM_RESOURCE_PATH': '/opt/px4/gazebo/models:/opt/px4/gazebo/worlds',
        'GZ_SIM_SYSTEM_PLUGIN_PATH': '/opt/px4/gazebo/plugins',
        'GZ_SIM_SERVER_CONFIG_PATH': '/opt/px4/gazebo/server.config', 'GZ_PARTITION': 'owned',
        'PX4_GZ_MODEL_POSE': '-6,0,0,0,0,0', 'PX4_VIDEO_HOST_IP': '127.0.0.1'}
    if change in ('world', 'spawn', 'camera_host', 'empty_partition'):
        environment[{'world': 'PX4_GZ_WORLD', 'spawn': 'PX4_GZ_MODEL_POSE', 'camera_host': 'PX4_VIDEO_HOST_IP',
                     'empty_partition': 'GZ_PARTITION'}[change]] = ''
    environment.update(scenario.scenario_environment(checked_scenario))
    if change in ('spawn', 'camera_host'): environment[{'spawn': 'PX4_GZ_MODEL_POSE', 'camera_host': 'PX4_VIDEO_HOST_IP'}[change]] = ''
    if change == 'autostart': environment['PX4_SYS_AUTOSTART'] = '4018'
    actual_model = value['model'] + '_0'
    def read(*args):
        if args[1] == 'inspect':
            mounts = [{'Source': str(tmp_path), 'Destination': '/work'}]
            for relative in checked_scenario.get('added_resources', {}):
                if change == 'missing_world_mount' and relative.startswith('worlds/') or change == 'missing_wrapper_mount' and relative.endswith('model.sdf'):
                    continue
                mounts.append({'Type': 'bind', 'RW': change == 'writable_world',
                    'Source': str(tmp_path / 'scene' / relative), 'Destination': '/opt/px4/gazebo/' + relative})
            return json.dumps([{'Id': 'original', 'Image': 'wrong' if change == 'image' else baseline['image_id'],
                'HostConfig': {'NetworkMode': 'none', 'Privileged': False, 'Devices': []},
                'NetworkSettings': {'Ports': {}}, 'Mounts': mounts}])
        if args[-1] == 'verify':
            return json.dumps([{'args': ['/opt/px4/bin/px4', '-i', '0'], 'cwd': '/work/rootfs',
                'model': 'gz_quadtailsitter' if change == 'model' else 'gz_' + value['model'],
                'environment': environment, 'binary_sha256': 'bad' if change == 'binary' else baseline['binary_sha256']}])
        if 'python3' in args:
            chain = {name: value['resources'][name]['sha256'] for name in value['airframe_chain']}
            if change == 'runtime_parent_airframe': chain[value['airframe_chain'][1]] = 'bad'
            resources = deepcopy(manifest['artifacts']['gazebo'])
            resources.update(deepcopy(checked_scenario.get('added_resources', {})))
            if board:
                world_file = value['added_world']['resource']
                if change == 'missing_world_file': del resources[world_file]
                if change == 'world_bytes': resources[world_file]['sha256'] = 'bad'
                if change == 'wrapper_bytes': resources[f'models/{value["model"]}/model.sdf']['sha256'] = 'bad'
            return json.dumps({'gazebo': {} if change == 'runtime_resources' else resources,
                'airframe_sha256': value['resources'][value['airframe_chain'][0]]['sha256'], 'scenario_airframes': chain})
        if 'service' in args:
            names = [*value['scene_models'], actual_model]
            if change == 'extra_entity': names.append('other')
            if change == 'missing_marker': names.remove('arucotag')
            return ''.join('model {\n  name: "' + name + '"\n}\n' for name in names)
        if 'topic' in args:
            topics = ['/world/aruco/pose/info', '/world/aruco/dynamic_pose/info',
                '/model/x500_mono_cam_0/odometry_with_covariance',
                '/world/aruco/model/x500_mono_cam_0/link/base_link/sensor/imu_sensor/imu',
                '/world/aruco/model/x500_mono_cam_0/link/camera_link/sensor/camera/image']
            if change == 'missing_image': topics.pop()
            if change == 'extra_image': topics.append('/world/aruco/model/x500_mono_cam_0/link/other/sensor/other/image')
            if change == 'extra_topic_model': topics.append('/model/other/odometry')
            return '\n'.join(topics).replace('/world/aruco/', '/world/' + value['world'] + '/').replace('x500_mono_cam_0', actual_model)
        if '/opt/px4/bin/px4-param' in args:
            return '\n'.join(f'{k}: {v}' for k, v in {**expected_params,
                'CA_ROTOR_COUNT': 6 if change == 'parameter' else expected_params['CA_ROTOR_COUNT']}.items())
        assert '/opt/px4/bin/px4-listener' in args
        return 'autopilot_uid: 123456789\n'
    commands = Mock(side_effect=read)
    monkeypatch.setattr(runner, 'command', commands)
    socket_path = tmp_path / 'native.sock'
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(socket_path))
        if change:
            with pytest.raises(ValueError):
                runner.verify_simulator('original', 0, socket_path,
                    simulation_build_manifest=Path(baseline['manifest']), gazebo_scenario=value['name'])
        else:
            checked = runner.verify_simulator('original', 0, socket_path,
                simulation_build_manifest=Path(baseline['manifest']), gazebo_scenario=value['name'])
            assert checked['firmware_build'] == baseline
            assert checked['gazebo']['runtime_scenario']['descriptor']['airframe_id'] == value['airframe_id']
            assert checked['gazebo']['expected_parameters']['MAV_TYPE'] == expected_params['MAV_TYPE']
            assert checked['gazebo']['model'] == actual_model
    assert not any(set(call.args) & {'arm', 'takeoff', 'set', '--pub', 'run', 'start'} for call in commands.call_args_list)


def test_actual_process_probe_reads_explicit_airframe_environment(tmp_path, monkeypatch):
    """Execute the read-only probe against synthetic proc files, not a canned result."""
    process = tmp_path / 'proc/123'
    process.mkdir(parents=True)
    (process / 'cmdline').write_bytes(b'/opt/px4/bin/px4\0-i\0' + b'0\0')
    (process / 'environ').write_bytes(b'PX4_SIM_MODEL=gz_standard_vtol_mono_cam\0PX4_SYS_AUTOSTART=4004\0')
    (process / 'exe').write_bytes(b'fixture executable')
    (process / 'cwd').mkdir()
    def read(*args):
        script = args[args.index('-c') + 1]
        script = script.replace("pathlib.Path('/proc')", 'pathlib.Path(' + repr(str(process.parent)) + ')')
        with monkeypatch.context() as context:
            context.setattr(sys, 'argv', ['probe', 'verify'])
            output = io.StringIO()
            with redirect_stdout(output):
                exec(compile(script, '<synthetic-proc-probe>', 'exec'), {})
        return output.getvalue()
    monkeypatch.setattr(runner, 'command', read)
    actual = runner.inspect_simulator_process('unused', 0, 1000, simulator='gazebo',
        baseline={'binary_sha256': hashlib.sha256(b'fixture executable').hexdigest()}, manifest={},
        scenario={'descriptor': {'model': 'standard_vtol_mono_cam'}})
    assert actual['environment']['PX4_SYS_AUTOSTART'] == '4004'


def raw_camera_package(package):
    value, manifest, baseline, _, _ = quadplane_package(package)
    root = scenario.SCENARIOS.parent
    original = ('<server_config><plugins><plugin filename="physics"/><plugin filename="sensors"/>'
        '<plugin entity_name="*" entity_type="world" filename="libGstCameraSystem.so" name="custom::GstCameraSystem"/>'
        '</plugins></server_config>')
    packaged = Path(baseline['manifest']).parent / 'packaged/gazebo/server.config'
    packaged.write_text(original)
    pin = {'sha256': hashlib.sha256(packaged.read_bytes()).hexdigest(), 'executable': False}
    manifest['artifacts']['gazebo']['server.config'] = pin
    value['resources']['gazebo/server.config'] = pin
    selected = root / 'server.config'
    selected.write_text('<server_config><plugins><plugin filename="physics"/><plugin filename="sensors"/></plugins></server_config>')
    value['name'] = 'standard-vtol-mono-camera-courtyard-v2'
    def save():
        value['server_config'] = {'sha256': hashlib.sha256(selected.read_bytes()).hexdigest(), 'executable': False}
        (scenario.SCENARIOS / (value['name'] + '.json')).write_text(json.dumps(value))
    save()
    return value, manifest, baseline, selected, save


def test_raw_camera_scenario_disables_only_encoder_and_stages_exact_readonly_overlay(tmp_path, package):
    value, manifest, baseline, selected, _ = raw_camera_package(package)
    before = deepcopy(manifest)
    checked = scenario.verified_scenario(value['name'], baseline, manifest)
    argv = scenario.stage_scenario_resources(checked, tmp_path / 'run')
    target = tmp_path / 'run/scenario/server.config'
    assert target.read_bytes() == selected.read_bytes()
    assert f'type=bind,src={target},dst=/opt/px4/gazebo/server.config,readonly' in argv
    assert checked['added_resources']['server.config'] == value['server_config']
    assert before == manifest


@pytest.mark.parametrize('change', ['physics', 'sensors', 'extra', 'encoder', 'attributes', 'malformed'])
def test_repinning_raw_server_cannot_remove_other_systems_or_add_plugins(package, change):
    value, manifest, baseline, selected, save = raw_camera_package(package)
    root = ET.parse(selected).getroot()
    plugins = root.find('plugins')
    if change in ('physics', 'sensors'):
        plugins.remove(next(node for node in plugins if node.get('filename') == change))
    elif change == 'extra': ET.SubElement(plugins, 'plugin', filename='extra')
    elif change == 'encoder': ET.SubElement(plugins, 'plugin', entity_name='*', entity_type='world',
        filename='libGstCameraSystem.so', name='custom::GstCameraSystem')
    elif change == 'attributes': plugins[0].set('enabled', 'false')
    selected.write_bytes(ET.tostring(root) if change != 'malformed' else b'<bad')
    save()
    with pytest.raises(ValueError, match='raw camera'):
        scenario.verified_scenario(value['name'], baseline, manifest)


def test_phase_fenced_courtyard_keeps_all_prior_scene_and_camera_resources():
    old = json.loads((scenario.SCENARIOS / 'standard-vtol-mono-camera-courtyard-v2.json').read_text())
    current = json.loads((scenario.SCENARIOS / 'standard-vtol-mono-camera-courtyard-v3.json').read_text())
    identity = {'name', 'build_manifest_sha256', 'image_id', 'binary_sha256'}
    assert {k: v for k, v in current.items() if k not in identity} == {k: v for k, v in old.items() if k not in identity}
    assert all(current[key] != old[key] for key in identity)


def test_current_mc_board_keeps_all_original_scene_and_camera_resources():
    old = json.loads((scenario.SCENARIOS / 'x500-mono-camera-board-v1.json').read_text())
    current = json.loads((scenario.SCENARIOS / 'x500-mono-camera-board-v2.json').read_text())
    identity = {'name', 'build_manifest_sha256', 'image_id', 'binary_sha256'}
    assert {k: v for k, v in current.items() if k not in identity} == {k: v for k, v in old.items() if k not in identity}
    assert all(current[key] != old[key] for key in identity)
    quadplane = json.loads((scenario.SCENARIOS / 'standard-vtol-mono-camera-courtyard-v3.json').read_text())
    assert all(current[key] == quadplane[key] for key in identity - {'name'})


def test_current_mc_descriptor_refuses_historical_build_before_resource_reads(tmp_path):
    old = json.loads((scenario.SCENARIOS / 'x500-mono-camera-board-v1.json').read_text())
    baseline = dict(kind='verified_gazebo_source_build', manifest=str(tmp_path/'absent.json'),
        image_id=old['image_id'], binary_sha256=old['binary_sha256'], manifest_sha256=old['build_manifest_sha256'])
    manifest = dict(kind='pixeagle_gazebo_build', build={}, image_id=old['image_id'],
                    artifacts={'binary_sha256': old['binary_sha256']})
    with pytest.raises(ValueError, match='exact verified stock build'):
        scenario.verified_scenario('x500-mono-camera-board-v2', baseline, manifest)
    assert list(tmp_path.iterdir()) == []


def test_metadata_mc_version_preserves_all_scene_resources():
    old = json.loads((scenario.SCENARIOS / 'x500-mono-camera-board-v2.json').read_text())
    new = json.loads((scenario.SCENARIOS / 'x500-mono-camera-board-v3.json').read_text())
    changed = {'name', 'build_manifest_sha256', 'image_id', 'binary_sha256'}
    assert {k: v for k, v in new.items() if k not in changed} == {k: v for k, v in old.items() if k not in changed}
    assert all(new[k] != old[k] for k in changed)
    quad = json.loads((scenario.SCENARIOS / 'standard-vtol-mono-camera-courtyard-v4.json').read_text())
    assert all(new[k] == quad[k] for k in changed - {'name'})


@pytest.mark.parametrize('change', [None, 'collision', 'undeclared', 'pose', 'hash'])
def test_visual_courtyard_preserves_native_world_and_refuses_hidden_changes(monkeypatch, tmp_path, change):
    root = scenario.SCENARIOS.parent
    old = json.loads((scenario.SCENARIOS / 'standard-vtol-mono-camera-courtyard-v3.json').read_text())
    new = json.loads((scenario.SCENARIOS / 'standard-vtol-mono-camera-courtyard-v4.json').read_text())
    for key in ('resources', 'camera', 'camera_mount', 'added_model', 'server_config', 'target', 'spawn_pose',
                'airframe_id', 'airframe_chain', 'identity_parameters'):
        assert new[key] == old[key]
    base = ET.parse(root / old['added_world']['resource'])
    names = {old['target']['name'], *(p['name'] for p in old['scene_additions'])}
    for model in list(base.findall('./world/model')):
        if model.get('name') in names:
            base.find('world').remove(model)
    base.find('world').set('name', 'aruco')
    files = {'gazebo/' + new['added_world']['base_resource']: ET.tostring(base.getroot())}
    files.update({k: b'pinned mesh placeholder' for k in new['resources'] if '/meshes/' in k})
    document = ET.parse(root / new['added_world']['resource'])
    new_names = {p['name'] for p in new['scene_additions']} - {p['name'] for p in old['scene_additions']}
    assert len(new_names) == 11
    for model in document.findall('./world/model'):
        if model.get('name') in new_names:
            assert model.findtext('static') == 'true'
            assert not any(model.findall('.//' + tag) for tag in ('collision', 'plugin', 'sensor', 'joint', 'include'))
    if change == 'collision':
        ET.SubElement(document.find('./world/model[@name="cross_roads"]/link'), 'collision', name='hidden')
    if change == 'undeclared':
        new['scene_additions'] = [p for p in new['scene_additions'] if p['name'] != 'cross_roads']
    if change == 'pose':
        document.find('./world/model[@name="cross_roads"]/pose').text = '0 0 1 0 0 0'
    path = tmp_path / new['added_world']['resource']
    path.parent.mkdir(parents=True)
    document.write(path)
    new['added_world']['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    if change == 'hash':
        new['added_world']['sha256'] = '0' * 64
    monkeypatch.setattr(scenario, 'SCENARIOS', tmp_path / 'scenarios')
    if change:
        with pytest.raises(ValueError):
            scenario._added_world(new, {'artifacts': {'gazebo': {}}}, files)
    else:
        assert new['added_world']['resource'] in scenario._added_world(new, {'artifacts': {'gazebo': {}}}, files)


@pytest.mark.parametrize('old_name,new_name', [
    ('x500-mono-camera-board-v2', 'x500-mono-camera-board-v3'),
    ('standard-vtol-mono-camera-courtyard-v3', 'standard-vtol-mono-camera-courtyard-v4')])
def test_metadata_scenarios_refuse_previous_build_before_reads(tmp_path, old_name, new_name):
    old = json.loads((scenario.SCENARIOS / (old_name + '.json')).read_text())
    baseline = dict(kind='verified_gazebo_source_build', manifest=str(tmp_path/'absent.json'),
        image_id=old['image_id'], binary_sha256=old['binary_sha256'], manifest_sha256=old['build_manifest_sha256'])
    manifest = dict(kind='pixeagle_gazebo_build', build={}, image_id=old['image_id'],
                    artifacts={'binary_sha256': old['binary_sha256']})
    with pytest.raises(ValueError, match='exact verified stock build'):
        scenario.verified_scenario(new_name, baseline, manifest)
    assert list(tmp_path.iterdir()) == []


def test_airframe_identity_resolves_literal_child_defaults_in_shell_order():
    name = 'etc/init.d-posix/airframes/4018_gz_quadtailsitter'
    base = 'etc/init.d/rc.vtol_defaults'
    value = dict(airframe_id=4018, model='quadtailsitter_nose_cam', base_model='quadtailsitter',
        airframe_chain=[name, base], identity_parameters=['MAV_TYPE'])
    files = {name: ('. ${R}' + base + '\nparam set-default MAV_TYPE 20\n').encode(),
             base: b'param set-default MAV_TYPE 22\n'}
    assert scenario.airframe_identity(value, files) == {'SYS_AUTOSTART': 4018, 'MAV_TYPE': 20}
    for duplicate in (name, base):
        changed = files | {duplicate: files[duplicate] + b'param set-default MAV_TYPE 20\n'}
        with pytest.raises(ValueError, match='identity is ambiguous'):
            scenario.airframe_identity(value, changed)


def test_tailsitter_uses_stock_plant_with_one_rotated_pinned_camera(tmp_path, package):
    name = 'quadtailsitter-nose-camera-courtyard-v1'
    value, manifest, baseline, _, additions = quadplane_package(package, name)
    original = deepcopy(manifest)
    checked = scenario.verified_scenario(name, baseline, manifest)
    assert checked['expected_parameters'] == dict(SYS_AUTOSTART=4018, MAV_TYPE=20,
        CA_AIRFRAME=4, CA_ROTOR_COUNT=4, CA_SV_CS_COUNT=0, VT_TYPE=0, SIM_GZ_EN=1)
    argv = host.simulation_launch_args('gazebo', baseline, manifest, runtime=tmp_path/'run',
        token='owner', name='tailsitter', gazebo_scenario=name)
    assert 'PX4_SYS_AUTOSTART=4018' in argv and 'PX4_SIM_MODEL=gz_quadtailsitter_nose_cam' in argv
    assert value['camera_mount']['pose'][4] == pytest.approx(-1.5707963267948966)
    assert manifest == original
    assert set(checked['added_resources']) == {*additions, 'server.config'}
    assert not {'--privileged', '--device', '-p'} & set(argv)
    for relative in checked['added_resources']:
        assert (tmp_path/'run/scenario'/relative).stat().st_mode & 0o777 == 0o444
