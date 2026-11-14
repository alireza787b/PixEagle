#!/usr/bin/env python3
"""Generate the pinned RGB-D instrumentation derivative; no aircraft changes."""

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from tools.build_gazebo_training_world import RESOURCE, build
from tools.gazebo_scenario import camera_pose_publisher


def generate(packaged):
    path = RESOURCE / 'scenarios/quadtailsitter-gimbal-camera-courtyard-v1.json'
    scenario = json.loads(path.read_text())
    relative = 'gazebo/models/mono_cam/model.sdf'
    raw = (packaged / relative).read_bytes()
    if hashlib.sha256(raw).hexdigest() != scenario['resources'][relative]['sha256']:
        raise ValueError('RGB-D derivative requires the declared stock camera resource')
    name = 'training_rgbd_camera'
    destination = RESOURCE / 'models' / name
    destination.mkdir(parents=True, exist_ok=True)
    document = ET.fromstring(raw)
    document.find('model').set('name', name)
    sensor = document.find('./model/link/sensor')
    sensor.set('type', 'rgbd_camera')
    sensor.find('update_rate').text = '20'
    document.find('model').append(camera_pose_publisher(scenario['instrumentation_camera']['instance']))
    ET.indent(document, space='  ')
    (destination / 'model.sdf').write_bytes(ET.tostring(document, encoding='utf-8', xml_declaration=True))
    (destination / 'model.config').write_text(
        f'<model><name>{name}</name><version>1.0</version><sdf version="1.9">model.sdf</sdf></model>\n')
    scenario['rgbd_camera'] = dict(base_model='mono_cam', model=name, update_rate_hz=20,
        files={member: dict(sha256=hashlib.sha256((destination / member).read_bytes()).hexdigest(), executable=False)
               for member in ('model.sdf', 'model.config')})
    scenario['camera']['model'] = name
    scenario['models'] = [name if value in ('mono_cam', name) else value for value in scenario['models']]
    world_path = RESOURCE / scenario['added_world']['resource']
    world = ET.parse(world_path)
    camera = next(node for node in world.find('world').findall('include')
                  if node.findtext('name') == scenario['instrumentation_camera']['instance'])
    camera.find('uri').text = 'model://' + name
    ET.indent(world, space='  ')
    world.write(world_path, encoding='utf-8', xml_declaration=True)
    scenario['added_world']['sha256'] = hashlib.sha256(world_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(scenario, indent=2) + '\n')
    build()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packaged', required=True, type=Path)
    generate(parser.parse_args().packaged)
