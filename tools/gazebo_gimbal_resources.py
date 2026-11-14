"""Reviewable derivatives of the pinned PX4 articulated-gimbal example.

Geometry and joints remain simulator mechanisms, not a measured FL-30 plant.
No firmware, guidance or aircraft actuator parameters are generated here.
"""

from copy import deepcopy
import math
import re
import xml.etree.ElementTree as ET

from classes.aircraft_state import finite_number


JOINTS = ('cgo3_vertical_arm_joint', 'cgo3_horizontal_arm_joint', 'cgo3_camera_joint')
AXES = ((0., 0., -1.), (-1., 0., 0.), (0., 1., 0.))
ROLES = ('yaw', 'roll', 'pitch')


def _set(node, name, value):
    child = node.find(name)
    if child is None:
        child = ET.SubElement(node, name)
    child.text = str(value)


def joint_pose_publisher():
    plugin = ET.Element('plugin', filename='gz-sim-pose-publisher-system', name='gz::sim::systems::PosePublisher')
    for key, value in dict(publish_model_pose='true', publish_link_pose='true',
            publish_sensor_pose='false', use_pose_vector_msg='true', update_frequency='-1').items():
        _set(plugin, key, value)
    return plugin


def joint_state_publisher():
    plugin = ET.Element('plugin', filename='gz-sim-joint-state-publisher-system', name='gz::sim::systems::JointStatePublisher')
    for name in JOINTS:
        ET.SubElement(plugin, 'joint_name').text = name
    return plugin


def derive_joint_gimbal(base_raw, optics_raw, *, name, rate_deg_s, mass_scale, limits_rad=None):
    if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', name) or name == 'gimbal':
        raise ValueError('derived_gimbal_name_invalid')
    rate = math.radians(finite_number(rate_deg_s, 'joint_rate'))
    scale = finite_number(mass_scale, 'gimbal_payload_mass_scale')
    if not 0 < rate <= 2*math.pi or not 0 < scale <= 1:
        raise ValueError('derived_gimbal_parameters_invalid')
    document = ET.fromstring(base_raw)
    model = document.find('model')
    if model is None or model.get('name') != 'gimbal' or model.findtext('static') != 'false':
        raise ValueError('derived_gimbal_base_invalid')
    model.set('name', name)
    original_mass = 0.
    for link in model.findall('link'):
        inertia = link.find('inertial')
        mass = float(inertia.findtext('mass'))
        original_mass += mass
        _set(inertia, 'mass', mass*scale)
        for component in inertia.findall('inertia/*'):
            component.text = str(float(component.text)*scale)
    joints = [model.find(f'joint[@name="{joint}"]') for joint in JOINTS]
    if any(node is None for node in joints):
        raise ValueError('derived_gimbal_joint_chain_invalid')
    for joint, axis in zip(joints, AXES):
        if tuple(float(v) for v in joint.findtext('axis/xyz').split()) != axis:
            raise ValueError('derived_gimbal_joint_axes_invalid')
    if limits_rad is not None:
        if len(limits_rad) != 3:
            raise ValueError('derived_gimbal_limits_invalid')
        for joint, (low, high) in zip(joints, limits_rad):
            if finite_number(low, 'joint_lower') >= finite_number(high, 'joint_upper'):
                raise ValueError('derived_gimbal_limits_invalid')
            _set(joint.find('axis/limit'), 'lower', low)
            _set(joint.find('axis/limit'), 'upper', high)
    for joint in joints:
        _set(joint.find('axis/limit'), 'velocity', rate)
    controllers = model.findall('plugin')
    if len(controllers) != 3 or {p.findtext('joint_name') for p in controllers} != set(JOINTS):
        raise ValueError('derived_gimbal_controllers_invalid')
    for plugin in controllers:
        if (plugin.get('name') != 'gz::sim::systems::JointPositionController'
                or plugin.get('filename') != 'gz-sim-joint-position-controller-system'):
            raise ValueError('derived_gimbal_controllers_invalid')
        joint_name = plugin.findtext('joint_name')
        if joint_name not in JOINTS:
            raise ValueError('derived_gimbal_controllers_invalid')
        role = ROLES[JOINTS.index(joint_name)]
        for item in list(plugin):
            if item.tag != 'joint_name':
                plugin.remove(item)
        _set(plugin, 'sub_topic', f'training/gimbal_{role}')
        _set(plugin, 'use_velocity_commands', 'true')
        _set(plugin, 'cmd_max', rate)
        _set(plugin, 'cmd_min', -rate)
    camera = model.find('./link[@name="camera_link"]/sensor[@name="camera"]')
    optics = ET.fromstring(optics_raw).find('./model/link/sensor/camera')
    if camera is None or optics is None or camera.get('type') != 'camera':
        raise ValueError('derived_gimbal_optics_invalid')
    camera.set('type', 'rgbd_camera')
    camera.remove(camera.find('camera'))
    camera.append(deepcopy(optics))
    _set(camera, 'update_rate', 20)
    sensor_pose = [float(v) for v in camera.findtext('pose').split()]
    if len(sensor_pose) != 6 or not all(math.isfinite(v) for v in sensor_pose):
        raise ValueError('derived_gimbal_sensor_pose_invalid')
    ET.indent(document, space='  ')
    return ET.tostring(document, encoding='utf-8', xml_declaration=True), dict(
        kinematic_chain='stock_gazebo_zxy', joint_names=list(JOINTS),
        limits_rad=[[float(j.findtext('axis/limit/lower')), float(j.findtext('axis/limit/upper'))] for j in joints],
        sensor_pose_link_flu=sensor_pose, body_link='base_link', camera_link='camera_link',
        mount_link='cgo3_mount_link', total_added_mass_kg=original_mass*scale,
        actuator='gazebo_joint_position_velocity_mode', rate_deg_s=rate_deg_s)
