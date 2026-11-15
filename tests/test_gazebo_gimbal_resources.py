"""Deterministic resource derivatives; no renderer or network required."""
import xml.etree.ElementTree as ET
import pytest
from tools.gazebo_gimbal_resources import derive_joint_gimbal, JOINTS, AXES


def inputs():
    document=ET.fromstring('<sdf><model name="gimbal"><static>false</static></model></sdf>')
    model=document.find('model')
    for name in ('mount','yaw','roll','camera_link'):
        link=ET.SubElement(model,'link',name=name)
        link.append(ET.fromstring('<inertial><mass>.1</mass><inertia><ixx>.001</ixx><iyy>.001</iyy><izz>.001</izz></inertia></inertial>'))
    for name,axis in zip(JOINTS,AXES):
        joint=ET.SubElement(model,'joint',name=name,type='revolute')
        joint.append(ET.fromstring('<axis><xyz>'+ ' '.join(map(str,axis))+'</xyz><limit><lower>-3.14</lower><upper>3.14</upper><velocity>-1</velocity></limit></axis>'))
        plugin=ET.SubElement(model,'plugin',name='gz::sim::systems::JointPositionController',filename='gz-sim-joint-position-controller-system')
        ET.SubElement(plugin,'joint_name').text=name
        ET.SubElement(plugin,'p_gain').text='9'
    model.find('link[@name="camera_link"]').append(ET.fromstring('<sensor name="camera" type="camera"><pose>-.04 0 -.16 0 0 3.14</pose><camera/><update_rate>30</update_rate></sensor>'))
    optics=b'<sdf><model><link><sensor><camera><horizontal_fov>1.74</horizontal_fov><image><width>1280</width><height>960</height></image></camera></sensor></link></model></sdf>'
    return document,optics


def test_derivative_has_one_standard_actuator_controller_per_joint_and_no_pid():
    document,optics=inputs()
    raw,meta=derive_joint_gimbal(ET.tostring(document),optics,name='training_gimbal',rate_deg_s=90.,mass_scale=.1)
    model=ET.fromstring(raw).find('model')
    assert meta['total_added_mass_kg']==pytest.approx(.04)
    assert [node.findtext('joint_name') for node in model.findall('plugin')]==list(JOINTS)
    for plugin in model.findall('plugin'):
        assert plugin.findtext('use_velocity_commands')=='true'
        assert plugin.find('p_gain') is None
        assert plugin.findtext('sub_topic').startswith('training/gimbal_')
    sensor=model.find('./link[@name="camera_link"]/sensor')
    assert sensor.get('type')=='rgbd_camera'
    assert sensor.findtext('camera/image/width')=='1280'
    assert sensor.findtext('pose')=='-.04 0 -.16 0 0 3.14'
    assert len(model.findall('plugin'))==3


@pytest.mark.parametrize('fault',['axis','unknown_plugin','negative_mass_scale','missing_controller'])
def test_unsupported_source_layout_cannot_be_silently_adopted(fault):
    document,optics=inputs();model=document.find('model');scale=.1
    if fault=='axis':model.find('joint/axis/xyz').text='1 0 0'
    if fault=='unknown_plugin':model.find('plugin').set('name','Unknown')
    if fault=='negative_mass_scale':scale=-.1
    if fault=='missing_controller':model.remove(model.find('plugin'))
    with pytest.raises(ValueError):
        derive_joint_gimbal(ET.tostring(document),optics,name='training_gimbal',rate_deg_s=90.,mass_scale=scale)
