#!/usr/bin/env python3
"""Pin the stock-aircraft + standard fixed-joint gimbal training composite."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from tools import sih_isolated_host as host  # noqa: E402
from tools.gazebo_gimbal_resources import derive_joint_gimbal, joint_pose_publisher, joint_state_publisher  # noqa: E402
from tools.build_gazebo_training_world import build  # noqa: E402
from tools.gazebo_scenario import SCENARIOS  # noqa: E402


def pin(path):
    return dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), executable=False)


def generate(build_manifest):
    _, baseline, manifest = host.verified_simulation_build(build_manifest, repository=ROOT)
    packaged = build_manifest.resolve().parent / 'packaged'
    path = SCENARIOS / 'quadtailsitter-gimbal-camera-courtyard-v1.json'
    value = json.loads(path.read_text())
    if value['build_manifest_sha256'] != baseline['manifest_sha256']:
        raise ValueError('Training composite requires its pinned stock build')
    sources = {}
    for name in ('gimbal', 'mono_cam'):
        relative = f'models/{name}/model.sdf'
        raw = (packaged / 'gazebo' / relative).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['artifacts']['gazebo'][relative]['sha256']:
            raise ValueError('Stock gimbal source changed')
        sources[name] = raw
    role = value.get('articulated_camera')
    if role is None:
        xml = ET.fromstring(sources['gimbal'])
        limits = [[float(j.findtext('axis/limit/lower')), float(j.findtext('axis/limit/upper'))]
                  for j in xml.findall('./model/joint')]
        role = dict(base_model='gimbal', optics_model='mono_cam', mechanics='ideal_joint_velocity',
                    rate_deg_s=90., mass_scale=.1, limits_rad=limits, files={})
    name = 'training_joint_gimbal'
    raw, geometry = derive_joint_gimbal(sources['gimbal'], sources['mono_cam'], name=name,
        rate_deg_s=role['rate_deg_s'], mass_scale=role['mass_scale'], limits_rad=role['limits_rad'])
    destination = SCENARIOS.parent / 'models' / name
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'model.sdf').write_bytes(raw)
    (destination / 'model.config').write_text(f'<model><name>{name}</name><version>1.0</version><sdf version="1.9">model.sdf</sdf></model>\n')
    role['files'] = {member: pin(destination / member) for member in ('model.sdf', 'model.config')}
    composite = 'quadtailsitter_joint_gimbal_training'
    mount = dict(frame='base_link_flu', pose=[.75, 0., 1.1, math.pi/2, 0., 3.14])
    pose = ' '.join(str(v) for v in mount['pose'])
    xml = ET.fromstring(f'''<sdf version="1.10"><model name="{composite}">
      <include merge="true"><uri>model://quadtailsitter</uri></include>
      <include merge="true"><uri>model://{name}</uri><pose relative_to="base_link">{pose}</pose></include>
      <joint name="CameraJoint" type="fixed"><parent>base_link</parent><child>{geometry['mount_link']}</child>
      <pose relative_to="base_link">{pose}</pose></joint></model></sdf>''')
    xml.find('model').extend((joint_pose_publisher(), joint_state_publisher()))
    destination = SCENARIOS.parent / 'models' / composite
    destination.mkdir(parents=True, exist_ok=True)
    ET.indent(xml, space='  ')
    (destination / 'model.sdf').write_bytes(ET.tostring(xml, encoding='utf-8', xml_declaration=True))
    (destination / 'model.config').write_text(f'<model><name>{composite}</name><version>1.0</version><sdf version="1.10">model.sdf</sdf></model>\n')
    world_path = SCENARIOS.parent / value['added_world']['resource']
    document = ET.parse(world_path)
    world = document.find('world')
    old = value.pop('instrumentation_camera', None)
    if old is not None:
        includes = [node for node in world.findall('include') if node.findtext('name') == old['instance']]
        if len(includes) != 1:
            raise ValueError('Old detached camera is missing or duplicated')
        world.remove(includes[0])
        value['scene_models'].remove(old['instance'])
    value.pop('rgbd_camera', None)
    ET.indent(document, space='  ')
    document.write(world_path, encoding='utf-8', xml_declaration=True)
    value['added_world']['sha256'] = pin(world_path)['sha256']
    value.update(schema_version=5, base_model='quadtailsitter', model=composite, camera_mount=mount,
        articulated_camera=role, added_model={member: pin(destination/member) for member in ('model.sdf', 'model.config')})
    value['models'] = [composite, 'quadtailsitter', 'airspeed', name, 'arucotag']
    value['camera']['model'] = name
    for relative, entry in manifest['artifacts']['gazebo'].items():
        if relative.startswith('models/gimbal/'):
            value['resources']['gazebo/' + relative] = entry
    path.write_text(json.dumps(value, indent=2)+'\n')
    build()
    return geometry


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-manifest', type=Path, required=True)
    print(json.dumps(generate(parser.parse_args().build_manifest), indent=2))
