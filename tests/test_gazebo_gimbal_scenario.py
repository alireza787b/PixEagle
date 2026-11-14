"""The instrumentation role cannot silently modify the aircraft plant."""

from copy import deepcopy
import json
import xml.etree.ElementTree as ET

import pytest

from tools import gazebo_scenario as scenario


@pytest.fixture
def resource():
    descriptor = json.loads((scenario.SCENARIOS / 'quadtailsitter-gimbal-camera-courtyard-v1.json').read_text())
    world = ET.parse(scenario.SCENARIOS.parent / descriptor['added_world']['resource']).find('world')
    return descriptor, world


def test_only_the_explicit_instrumentation_include_is_removed(resource):
    value, world = resource
    before = deepcopy(world)
    scenario._remove_instrumentation_camera(world, value)
    selected = [item for item in before.findall('include') if item.findtext('name') == value['instrumentation_camera']['instance']]
    assert len(selected) == 1
    before.remove(selected[0])
    assert scenario._canonical(before) == scenario._canonical(world)


@pytest.mark.parametrize('fault', ['aircraft', 'nan', 'rate', 'mechanics', 'dynamic', 'plugin', 'extra_include'])
def test_instrumentation_declaration_cannot_hide_other_mechanics(resource, fault):
    value, world = resource
    declaration = value['instrumentation_camera']
    camera = next(item for item in world.findall('include') if item.findtext('name') == declaration['instance'])
    if fault == 'aircraft': declaration['instance'] = value['model']
    if fault == 'nan': declaration['offset_body_frd_m'][0] = float('nan')
    if fault == 'rate': declaration['pointing_rate_deg_s'] = 0
    if fault == 'mechanics': declaration['mechanics'] = 'measured_fl30'
    if fault == 'dynamic': camera.find('static').text = 'false'
    if fault == 'plugin': ET.SubElement(camera, 'plugin', dict(name='hidden'))
    if fault == 'extra_include': world.append(deepcopy(camera))
    with pytest.raises(ValueError):
        scenario._remove_instrumentation_camera(world, value)
