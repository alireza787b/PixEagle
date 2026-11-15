"""The gimbal fixture must be a declared, physically attached model composite."""

from copy import deepcopy
import json
import xml.etree.ElementTree as ET

import pytest
from tools import gazebo_scenario as scenario


@pytest.fixture
def resource():
    descriptor=json.loads((scenario.SCENARIOS/'quadtailsitter-gimbal-camera-courtyard-v1.json').read_text())
    directory=scenario.SCENARIOS.parent/'models'/descriptor['model']
    return descriptor,{name:(directory/name).read_bytes() for name in ('model.sdf','model.config')}


def test_gimbal_base_is_attached_and_camera_is_not_a_second_world_model(resource):
    value,files=resource
    assert value['schema_version']==5
    model=ET.fromstring(files['model.sdf']).find('model')
    assert [(n.findtext('parent'),n.findtext('child')) for n in model.findall('joint')]==[('base_link','cgo3_mount_link')]
    assert [n.findtext('uri') for n in model.findall('include')]==['model://quadtailsitter','model://training_joint_gimbal']
    world=ET.parse(scenario.SCENARIOS.parent/value['added_world']['resource']).find('world')
    assert all(n.findtext('name')!='training_gimbal_camera' for n in world.findall('include'))
    assert {p.get('name') for p in model.findall('plugin')}=={
        'gz::sim::systems::PosePublisher','gz::sim::systems::JointStatePublisher'}
    assert 'instrumentation_camera' not in value


@pytest.mark.parametrize('fault',['none','parent','child','dynamic_joint','hidden_plugin','mount_pose'])
def test_wrapper_verifier_rejects_unreviewed_attachment_or_controller_changes(resource,monkeypatch,fault):
    value,files=resource
    document=ET.fromstring(files['model.sdf']);model=document.find('model')
    if fault=='parent':model.find('joint/parent').text='world'
    if fault=='child':model.find('joint/child').text='camera_link'
    if fault=='dynamic_joint':model.find('joint').set('type','ball')
    if fault=='hidden_plugin':ET.SubElement(model,'plugin',name='DetachedCameraFollower')
    if fault=='mount_pose':model.findall('include')[1].find('pose').text='0 0 0 0 0 0'
    altered=dict(files,**{'model.sdf':ET.tostring(document)})
    monkeypatch.setattr(scenario,'_read_file',lambda root,relative,pin:altered[relative.rsplit('/',1)[1]])
    originals={'etc/init.d-posix/rcS':b'', 'etc/init.d-posix/px4-rc.gzsim':b''}
    if fault=='none':
        result=scenario._added_camera_model(value,{'artifacts':{'gazebo':{}}},originals)
        assert len(result)==2
    else:
        with pytest.raises(ValueError):
            scenario._added_camera_model(value,{'artifacts':{'gazebo':{}}},originals)
