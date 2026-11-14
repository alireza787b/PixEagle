#!/usr/bin/env python3
"""Rebuild the pinned PixEagle coastal visual-training world and local art.

Static visual props only: no aircraft changes, physical wind/waves, collisions,
detector truth or moving-target qualification is implied by the scene.
"""

import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
RESOURCE = ROOT / 'native/gazebo'
ART = 'models/pixeagle_training_art/materials/textures'


def text(node, name, value):
    ET.SubElement(node, name).text = str(value)


def visual(model, name, shape, size, *, pose=(0, 0, 0, 0, 0, 0), color='.15 .6 .7 1', texture=None):
    link = model.find('link')
    if link is None:
        link = ET.SubElement(model, 'link', {'name': 'art'})
    item = ET.SubElement(link, 'visual', {'name': name})
    text(item, 'pose', ' '.join(str(n) for n in pose))
    geometry = ET.SubElement(item, 'geometry')
    form = ET.SubElement(geometry, shape)
    if shape in ('box', 'plane'):
        text(form, 'size', ' '.join(str(n) for n in size))
        if shape == 'plane':
            text(form, 'normal', '0 0 1')
    elif shape == 'sphere':
        text(form, 'radius', size[0])
    elif shape == 'cylinder':
        text(form, 'radius', size[0])
        text(form, 'length', size[1])
    else:
        raise ValueError('Unsupported training-art primitive')
    material = ET.SubElement(item, 'material')
    text(material, 'ambient', color)
    text(material, 'diffuse', color)
    if texture is not None:
        metal = ET.SubElement(ET.SubElement(material, 'pbr'), 'metal')
        text(metal, 'albedo_map', f'model://{ART.removeprefix("models/")}/{texture}')
        text(metal, 'metalness', 0)
        text(metal, 'roughness', .8)


def label(model, name, *, width=20., height=5., pose=(0, 0, 0, math.pi/2, 0, 0)):
    visual(model, name, 'plane', (width, height), pose=pose, color='1 1 1 1', texture='pixeagle-banner.png')


def art_assets():
    from PIL import Image, ImageDraw, ImageFont
    directory = RESOURCE / ART
    directory.mkdir(parents=True, exist_ok=True)
    font = ROOT / 'resources/fonts/RobotoMono-Regular.ttf'
    image = Image.new('RGB', (2048, 512), '#102b45')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((20, 20, 2028, 492), radius=35, outline='#49d6cb', width=12)
    draw.line((120, 140, 190, 230, 260, 140), fill='#49d6cb', width=26)
    draw.line((100, 265, 190, 175, 280, 265), fill='#49d6cb', width=20)
    draw.text((350, 55), 'PixEagle', font=ImageFont.truetype(str(font), 230), fill='#ffffff', stroke_width=2)
    draw.text((365, 333), 'VISION  /  TRACK  /  FOLLOW', font=ImageFont.truetype(str(font), 66), fill='#66e1d9')
    image.save(directory / 'pixeagle-banner.png', optimize=True)
    return {str(path.relative_to(RESOURCE)): dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), executable=False)
            for path in sorted(directory.glob('*.png'))}


def build():
    base = json.loads((RESOURCE / 'scenarios/quadtailsitter-gimbal-camera-courtyard-v1.json').read_text())
    document = ET.parse(RESOURCE / base['added_world']['resource'])
    world = document.find('world')
    world.set('name', 'pixeagle_training_coast_v1')
    declarations = []

    def model(name, pose):
        value = ET.SubElement(world, 'model', {'name': name})
        text(value, 'static', 'true')
        text(value, 'pose', ' '.join(str(n) for n in pose))
        declarations.append(dict(name=name, pose=list(pose)))
        return value

    # Near-field high-detail patches, ground text and a raised road sculpture.
    entry = model('pixeagle_welcome', (18, 35, 0, 0, 0, 0))
    visual(entry, 'frame', 'box', (22, .3, 6), pose=(0, 0, 4, 0, 0, 0), color='.04 .08 .12 1')
    label(entry, 'front', pose=(0, -.16, 4, math.pi/2, 0, 0))
    for x in (-9, 9):
        visual(entry, f'post_{x}', 'box', (.3, .3, 5), pose=(x, 0, 2.5, 0, 0, 0), color='.25 .28 .3 1')
    road = model('pixeagle_road_art', (42, 0, .025, 0, 0, 0))
    label(road, 'ground_mural', width=22, height=8, pose=(0, 0, 0, 0, 0, 0))
    sculpture = model('pixeagle_vision_sculpture', (-25, 38, 0, 0, 0, 0))
    for i in range(3):
        visual(sculpture, f'offset_cube_{i}', 'box', (4, 4, 4),
            pose=(i*1.2, 0, 2 + i*4, 0, 0, i*.35), color=('.06 .5 .6 1' if i % 2 else '.9 .5 .12 1'))
    visual(sculpture, 'sphere', 'sphere', (2.8,), pose=(3.5, 0, 15, 0, 0, 0), color='.15 .75 .65 1')

    # Airborne test objects provide finite elevated targets from several bearings.
    for index, (x, y, z, color) in enumerate([(45, 100, 55, '.12 .75 .7 1'), (-85, 85, 85, '.95 .52 .12 1'), (190, -30, 110, '.3 .48 .9 1')]):
        balloon = model(f'pixeagle_balloon_{index}', (x, y, z, 0, 0, math.atan2(-x, y)))
        visual(balloon, 'envelope', 'sphere', (7,), color=color)
        visual(balloon, 'collar', 'cylinder', (2, 3), pose=(0, 0, -7, 0, 0, 0), color='.15 .18 .2 1')
        visual(balloon, 'basket', 'box', (3, 3, 2), pose=(0, 0, -13, 0, 0, 0), color='.35 .2 .1 1')
        for a, b in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            visual(balloon, f'rope_{a}_{b}', 'cylinder', (.045, 5), pose=(a, b, -10, 0, 0, 0), color='.2 .2 .2 1')
        label(balloon, 'advertisement', width=11, height=3, pose=(0, -7.1, 0, math.pi/2, 0, 0))
    ship = model('pixeagle_airship', (-130, 190, 100, 0, 0, -.5))
    visual(ship, 'body', 'cylinder', (4, 26), pose=(0, 0, 0, 0, math.pi/2, 0), color='.82 .87 .9 1')
    for x in (-13, 13):
        visual(ship, f'end_{x}', 'sphere', (4,), pose=(x, 0, 0, 0, 0, 0), color='.82 .87 .9 1')
    visual(ship, 'gondola', 'box', (8, 3, 2), pose=(0, 0, -5, 0, 0, 0), color='.05 .2 .3 1')
    visual(ship, 'tail_vertical', 'box', (6, .3, 9), pose=(-14, 0, 0, 0, 0, 0))
    visual(ship, 'tail_horizontal', 'box', (6, 10, .3), pose=(-14, 0, 0, 0, 0, 0))
    label(ship, 'side_brand', width=19, height=4, pose=(0, -4.05, 0, math.pi/2, 0, 0))

    # The coastal patch is visual art, not a hydrodynamic or collision surface.
    water = model('training_sea', (590, 0, .018, 0, 0, 0))
    visual(water, 'ocean', 'box', (600, 1100, .015), color='.06 .32 .47 1')
    for i in range(20):
        visual(water, f'wave_glint_{i}', 'box', (30 + i % 4 * 11, .24, .02),
            pose=(-260 + (i % 5)*118, -470 + (i // 5)*260 + (i % 3)*17, .02, 0, 0, .1), color='.42 .65 .7 1')
    coast = model('training_coast_road', (280, 0, .03, 0, 0, 0))
    visual(coast, 'tarmac', 'box', (12, 1000, .02), color='.12 .14 .16 1')
    for i in range(-18, 19):
        visual(coast, f'center_dash_{i}', 'box', (.2, 9, .02), pose=(0, i*26, .025, 0, 0, 0), color='.95 .87 .45 1')
    dock = model('training_pier', (340, 40, 1, 0, 0, 0))
    visual(dock, 'deck', 'box', (110, 12, 2), color='.4 .35 .25 1')
    label(dock, 'dock_brand', width=24, height=7, pose=(0, 0, 1.02, 0, 0, 0))
    for index, (x, y, yaw) in enumerate([(430, 65, .2), (590, -100, -.6), (680, 220, 1.)]):
        boat = model(f'pixeagle_surface_vessel_{index}', (x, y, 0, 0, 0, yaw))
        visual(boat, 'hull', 'box', (26, 8, 2), pose=(0, 0, 1.2, 0, 0, 0), color='.06 .12 .18 1')
        visual(boat, 'deck', 'box', (22, 7, .6), pose=(0, 0, 2.5, 0, 0, 0), color='.8 .8 .72 1')
        visual(boat, 'bridge', 'box', (6, 5, 5), pose=(-4, 0, 5, 0, 0, 0), color='.9 .94 .92 1')
        visual(boat, 'window', 'box', (6.1, 5.1, 1.2), pose=(-4, 0, 6, 0, 0, 0), color='.08 .28 .42 1')
        visual(boat, 'mast', 'cylinder', (.1, 8), pose=(-4, 0, 10, 0, 0, 0), color='.3 .35 .4 1')
        label(boat, 'deck_brand', width=10, height=4, pose=(6, 0, 2.82, 0, 0, 0))

    for index, (x, y, yaw) in enumerate([(55, -5, 0), (95, 5, math.pi), (275, 90, math.pi/2), (285, -120, -math.pi/2), (265, 200, .3)]):
        car = model(f'tracker_test_car_{index}', (x, y, .03, 0, 0, yaw))
        visual(car, 'body', 'box', (4.6, 1.9, 1), pose=(0, 0, .85, 0, 0, 0), color=['.9 .2 .12 1', '.1 .5 .85 1', '.8 .7 .12 1'][index % 3])
        visual(car, 'cabin', 'box', (2.1, 1.7, .8), pose=(-.2, 0, 1.6, 0, 0, 0), color='.1 .2 .28 1')
        for a, b in [(-1.5, -1), (-1.5, 1), (1.5, -1), (1.5, 1)]:
            visual(car, f'wheel_{a}_{b}', 'cylinder', (.4, .25), pose=(a, b, .4, math.pi/2, 0, 0), color='.03 .03 .03 1')
    base.update(name='quadtailsitter-gimbal-training-coast-v1', world=world.get('name'), scene_assets=art_assets())
    base['scene_additions'] += declarations
    base['scene_models'] += [item['name'] for item in declarations]
    relative = 'worlds/pixeagle_training_coast_v1.sdf'
    ET.indent(document, space='  ')
    document.write(RESOURCE / relative, encoding='utf-8', xml_declaration=True)
    base['added_world'].update(resource=relative, sha256=hashlib.sha256((RESOURCE / relative).read_bytes()).hexdigest())
    destination = RESOURCE / 'scenarios' / (base['name'] + '.json')
    destination.write_text(json.dumps(base, indent=2) + '\n')
    return base


if __name__ == '__main__':
    value = build()
    print(f"Built {value['name']}: {len(value['scene_additions'])} declared visual props, {len(value['scene_assets'])} local texture")
