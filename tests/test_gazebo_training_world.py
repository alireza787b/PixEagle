"""Reproducible visual scene and pinned texture roles; no flight claims."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import pytest

from tools import build_gazebo_training_world as builder
from tools import gazebo_scenario as scenario


def test_coastal_world_build_is_repeatable_and_preserves_the_aircraft(tmp_path, monkeypatch):
    source = builder.RESOURCE
    resource = tmp_path / 'resources'
    (resource / 'scenarios').mkdir(parents=True)
    (resource / 'worlds').mkdir()
    template = 'quadtailsitter-gimbal-camera-courtyard-v1.json'
    shutil.copy(source / 'scenarios' / template, resource / 'scenarios' / template)
    shutil.copy(source / 'worlds/training_gimbal_courtyard_v1.sdf', resource / 'worlds/training_gimbal_courtyard_v1.sdf')
    original = json.loads((resource / 'scenarios' / template).read_text())
    monkeypatch.setattr(builder, 'RESOURCE', resource)
    first = builder.build()
    world = resource / first['added_world']['resource']
    image = resource / next(iter(first['scene_assets']))
    first_bytes = world.read_bytes(), image.read_bytes()
    assert builder.build() == first
    assert (world.read_bytes(), image.read_bytes()) == first_bytes
    for field in ('model', 'airframe_id', 'resources', 'image_id', 'binary_sha256', 'airframe_chain'):
        assert first[field] == original[field]
    assert first['instrumentation_camera'] == original['instrumentation_camera']
    names = set(first['scene_models'])
    assert {'pixeagle_airship', 'pixeagle_balloon_0', 'training_sea', 'training_pier',
            'pixeagle_surface_vessel_0', 'tracker_test_car_0', 'pixeagle_road_art'} <= names
    for model in ET.parse(world).findall('./world/model'):
        assert model.findtext('static') == 'true'
    assert image.stat().st_size < 100_000


@pytest.mark.parametrize('fault', ['none', 'path', 'executable', 'hash', 'dimensions'])
def test_scene_art_accepts_only_pinned_bounded_local_png(tmp_path, monkeypatch, fault):
    original = json.loads((scenario.SCENARIOS / 'quadtailsitter-gimbal-training-coast-v1.json').read_text())
    relative, pin = next(iter(original['scene_assets'].items()))
    source = scenario.SCENARIOS.parent / relative
    (tmp_path / 'scenarios').mkdir()
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(source.read_bytes())
    monkeypatch.setattr(scenario, 'SCENARIOS', tmp_path / 'scenarios')
    value = deepcopy(original)
    if fault == 'path': value['scene_assets'] = {'models/../hidden.png': pin}
    if fault == 'executable': value['scene_assets'][relative]['executable'] = True
    if fault == 'hash': value['scene_assets'][relative]['sha256'] = '0' * 64
    if fault == 'dimensions':
        raw = bytearray(target.read_bytes()); raw[16:20] = bytes(4); target.write_bytes(raw)
        value['scene_assets'][relative]['sha256'] = hashlib.sha256(raw).hexdigest()
    if fault == 'none':
        files = {}
        assert scenario._scene_assets(value, files) == value['scene_assets']
        assert files['gazebo/' + relative] == target.read_bytes()
    else:
        with pytest.raises(ValueError):
            scenario._scene_assets(value, {})


def test_static_prop_texture_cannot_resolve_to_remote_or_unpinned_content():
    world = ET.fromstring('''<world><model name="sign"><static>true</static><pose>0 0 0 0 0 0</pose>
        <link name="link"><visual name="image"><material><pbr><metal>
        <albedo_map>https://example.invalid/texture.png</albedo_map>
        </metal></pbr></material></visual></link></model></world>''')
    with pytest.raises(ValueError, match='pinned local'):
        scenario._remove_static_scene_additions(world, [dict(name='sign', pose=[0]*6)], {})
