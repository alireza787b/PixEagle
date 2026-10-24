#!/usr/bin/env python3
"""Build a read-only interactive SIH guidance report.

Examples:
  PYTHONPATH=src python tools/sih_visualizer.py \
    --scenario tools/sih_visualization_scenarios/gimbal-vector-vertical.yaml \
    --evidence-root reports/sitl/run --output-dir reports/sitl/run/visualization

  PYTHONPATH=src python tools/sih_visualizer.py \
    --scenario tools/sih_visualization_scenarios/gimbal-vector-vertical.yaml \
    --live-url http://127.0.0.1:8080/v1/mavlink --system-id 1 --duration-s 30 \
    --output-dir reports/sitl/live/visualization
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from classes.sih_visualization import (  # noqa: E402
    VisualizationSample,
    VisualizationScenario,
    analyze_timeline,
    build_timeline,
    load_evidence,
    write_csv,
)
try:
    from tools.sitl_gimbal_geometry_fixture import pose_from_mavlink2rest  # noqa: E402
except ModuleNotFoundError:
    from sitl_gimbal_geometry_fixture import pose_from_mavlink2rest  # noqa: E402


def _json_script(value: Any) -> str:
    return json.dumps(value, separators=(",", ":")).replace("</", "<\\/")


def build_html(scenario: VisualizationScenario, samples: list[VisualizationSample], summary: dict[str, Any]) -> str:
    payload = {
        "scenario": {
            "name": scenario.name,
            "frame": scenario.frame,
            "mount_type": scenario.mount_type,
            "follower_profile": scenario.follower_profile,
            "lateral_guidance_mode": scenario.lateral_guidance_mode,
            "altitude_control": scenario.altitude_control,
            "requested_speed": scenario.requested_speed,
            "initial_vehicle_ned": scenario.initial_vehicle_ned,
            "limits": scenario.limits,
        },
        "samples": [sample.to_dict() for sample in samples],
        "summary": summary,
    }
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PixEagle SIH guidance report</title>
<style>
:root {{ color-scheme: dark; --bg:#111820; --panel:#1d2732; --muted:#98a8b7; --line:#3b4b5b; --target:#ffbd69; --drone:#68b5ff; --cmd:#ff6b6b; }}
* {{ box-sizing:border-box }} body {{ margin:0; font:14px system-ui,sans-serif; background:var(--bg); color:#eef4f8 }}
header {{ padding:14px 18px; border-bottom:1px solid var(--line); display:flex; gap:20px; align-items:baseline; flex-wrap:wrap }}
h1 {{ font-size:19px; margin:0 }} .muted {{ color:var(--muted) }} main {{ display:grid; grid-template-columns:minmax(520px,2fr) minmax(300px,1fr); gap:12px; padding:12px }}
.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px }} canvas {{ width:100%; display:block; background:#0b1117; border-radius:5px }}
#scene {{ height:min(66vh,650px); touch-action:none; cursor:grab }} #scene:active {{ cursor:grabbing }} #timeline {{ height:180px; margin-top:10px }} button,input {{ font:inherit }} button {{ color:#eef4f8; background:#2d4051; border:1px solid #557087; border-radius:5px; padding:6px 9px; cursor:pointer }} button:hover {{ background:#3b566c }}
.controls {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:8px }} .control-group {{ display:inline-flex; align-items:center; gap:4px; padding-right:4px; border-right:1px solid var(--line) }} .control-label {{ color:var(--muted); margin-right:2px }} .layers {{ margin:3px 0 8px; color:var(--muted) }} .layers summary {{ cursor:pointer; padding:4px 0 }} label {{ color:var(--muted); margin-right:6px }}
.badge {{ display:inline-block; border:1px solid #557087; border-radius:12px; padding:3px 8px; margin:2px; font-size:12px }} .warning {{ border-color:#d98b3d; color:#ffd38d }}
.legend {{ display:flex; flex-wrap:wrap; gap:8px; padding:6px 0; color:var(--muted); font-size:12px }} .legend span {{ display:inline-flex; align-items:center; gap:4px }} .swatch {{ width:12px; height:3px; display:inline-block }}
pre {{ white-space:pre-wrap; max-height:280px; overflow:auto; color:#d8e3ec }} table {{ width:100%; border-collapse:collapse }} td {{ padding:4px 2px; border-bottom:1px solid #2d3a47 }}
@media(max-width:900px) {{ main {{ grid-template-columns:1fr }} #scene {{ height:56vh }} }}
</style></head><body>
<header><h1>PixEagle SIH guidance report</h1><span class="muted" id="scenario"></span><span class="badge" id="coverage"></span><span class="badge warning">Read-only evidence viewer</span></header>
<main><section class="panel"><div class="controls primary-controls"><button id="play" aria-label="Play or pause evidence">Play</button><button id="reset" aria-label="Reset evidence playback">Reset</button><button id="resetView" aria-label="Reset 3D view">Reset 3D</button><span class="control-group"><span class="control-label">View</span><button data-view="iso">3D</button><button data-view="top">Top</button><button data-view="front">Front</button><button data-view="side">Side</button></span><label>speed <select id="rate"><option>0.25</option><option>0.5</option><option selected>1</option><option>2</option><option>4</option></select>x</label></div><details class="layers"><summary>Layers</summary><div class="controls layer-controls"><label><input id="targetHistory" type="checkbox" checked> target path</label><label><input id="droneHistory" type="checkbox" checked> PX4 path</label><label><input id="losToggle" type="checkbox" checked> line of sight</label><label><input id="commandToggle" type="checkbox" checked> command intent</label></div></details><canvas id="scene" width="1000" height="650"></canvas><div class="legend"><span><i class="swatch" style="background:#ffbd69"></i> target truth</span><span><i class="swatch" style="background:#68b5ff"></i> PX4 pose (observed)</span><span><i class="swatch" style="background:#ff6b6b"></i> command intent (body FRD)</span><span class="muted">Solid marker = now · dashed line = history · 3D = draggable N/E/D orbit</span></div><input id="scrub" type="range" min="0" max="0" value="0" style="width:100%"><div class="muted" id="time"></div></section>
<aside><section class="panel"><h3>Current sample</h3><div id="badges"></div><table id="values"></table></section><section class="panel"><h3>Timeline</h3><canvas id="timeline" width="700" height="180"></canvas></section><section class="panel"><h3>Validation</h3><pre id="summary"></pre></section></aside></main>
<script>const PAYLOAD={_json_script(payload)};let i=0,playing=false,view='iso',timer=null;
const scene=document.getElementById('scene'),ctx=scene.getContext('2d'),timeline=document.getElementById('timeline'),tctx=timeline.getContext('2d');
const samples=PAYLOAD.samples||[];const speedLabel=PAYLOAD.scenario.requested_speed==null?(PAYLOAD.summary.speed_reference_m_s==null?'No session speed':`Ceiling: ${{PAYLOAD.summary.speed_reference_m_s}} m/s`):`Request: ${{PAYLOAD.scenario.requested_speed}} m/s`;document.getElementById('scenario').textContent=`${{PAYLOAD.scenario.name}} · Follower: ${{PAYLOAD.scenario.follower_profile}} · Lateral: ${{PAYLOAD.scenario.lateral_guidance_mode}} · Mount: ${{PAYLOAD.scenario.mount_type}} · Altitude: ${{PAYLOAD.scenario.altitude_control?'on':'off'}} · ${{speedLabel}}`;
document.getElementById('summary').textContent=JSON.stringify(PAYLOAD.summary,null,2);const coverage=document.getElementById('coverage'),poseCount=Number(PAYLOAD.summary.pose_observed_samples||0);coverage.textContent=poseCount?`PX4 pose: ${{poseCount}} samples`:'PX4 pose unavailable';if(!poseCount)coverage.classList.add('warning');document.getElementById('scrub').max=Math.max(0,samples.length-1);
function points(key){{return samples.slice(0,i+1).map(s=>s[key]||null)}}
let orbitYaw=-0.65,orbitPitch=1.32,sceneScale=35,sceneOrigin=[scene.width/2,scene.height/2],autoScale=true,worldBounds=null;
function oriented(p){{if(!p)return null;const n=p[0],e=p[1],d=p[2];if(view!=='iso')return[n,e,d];const yawX=Math.cos(orbitYaw)*n-Math.sin(orbitYaw)*e;const depth=Math.sin(orbitYaw)*n+Math.cos(orbitYaw)*e;const pitchY=Math.cos(orbitPitch)*depth+Math.sin(orbitPitch)*d;const pitchDepth=-Math.sin(orbitPitch)*depth+Math.cos(orbitPitch)*d;return[yawX,pitchY,pitchDepth]}}
function projected(p){{if(!p)return null;const o=oriented(p);if(view==='front')return[o[0],o[2]];if(view==='side')return[o[1],o[2]];return[o[0],o[1]]}}
function fitScene(){{if(!autoScale)return;const all=[];for(const s of samples){{if(s.target_ned)all.push(s.target_ned);if(s.vehicle_ned)all.push(s.vehicle_ned)}}if(!all.length){{sceneScale=35;sceneOrigin=[scene.width/2,scene.height/2];worldBounds=null;return}}worldBounds={{minN:Math.min(...all.map(p=>p[0])),maxN:Math.max(...all.map(p=>p[0])),minE:Math.min(...all.map(p=>p[1])),maxE:Math.max(...all.map(p=>p[1])),minD:Math.min(...all.map(p=>p[2])),maxD:Math.max(...all.map(p=>p[2]))}};const xy=all.map(projected);const minX=Math.min(...xy.map(p=>p[0])),maxX=Math.max(...xy.map(p=>p[0])),minY=Math.min(...xy.map(p=>p[1])),maxY=Math.max(...xy.map(p=>p[1]));const spanX=Math.max(1,maxX-minX),spanY=Math.max(1,maxY-minY);sceneScale=Math.max(8,Math.min(55,(scene.width-120)/spanX,(scene.height-120)/spanY));sceneOrigin=[scene.width/2-(minX+maxX)*sceneScale/2,scene.height/2-(minY+maxY)*sceneScale/2]}}
function project(p){{const q=projected(p);return q?[sceneOrigin[0]+q[0]*sceneScale,sceneOrigin[1]+q[1]*sceneScale]:null}}
function drawArrow(a,b,color){{if(!a||!b)return;ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();const ang=Math.atan2(b[1]-a[1],b[0]-a[0]);ctx.beginPath();ctx.moveTo(b[0],b[1]);ctx.lineTo(b[0]-12*Math.cos(ang-.5),b[1]-12*Math.sin(ang-.5));ctx.lineTo(b[0]-12*Math.cos(ang+.5),b[1]-12*Math.sin(ang+.5));ctx.closePath();ctx.fill()}}
function path(key,color){{const opacity=.38;const ps=points(key).map(project);ctx.save();ctx.globalAlpha=opacity;ctx.strokeStyle=color;ctx.lineWidth=2;ctx.setLineDash([8,6]);ctx.beginPath();let started=false;for(const p of ps){{if(!p){{started=false;continue}}if(!started){{ctx.moveTo(p[0],p[1]);started=true}}else ctx.lineTo(p[0],p[1])}}ctx.stroke();ctx.restore()}}
function marker(point,color,label,shape){{if(!point)return;ctx.save();ctx.fillStyle=color;ctx.strokeStyle='#071016';ctx.lineWidth=2;ctx.beginPath();if(shape==='diamond'){{ctx.moveTo(point[0],point[1]-10);ctx.lineTo(point[0]+10,point[1]);ctx.lineTo(point[0],point[1]+10);ctx.lineTo(point[0]-10,point[1]);ctx.closePath()}}else{{ctx.arc(point[0],point[1],9,0,Math.PI*2)}}ctx.fill();ctx.stroke();ctx.font='600 12px system-ui,sans-serif';ctx.fillStyle='#eef4f8';ctx.fillText(label,point[0]+12,point[1]-10);ctx.restore()}}
function drawAxisTriad(){{if(view!=='iso')return;const origin=[70,scene.height-64];const axes=[['N',[1,0,0],'#d9efff'],['E',[0,1,0],'#ffbd69'],['D',[0,0,1],'#6ee7a1']];ctx.save();ctx.font='600 12px system-ui,sans-serif';for(const[label,vector,color]of axes){{const direction=projected(vector),end=[origin[0]+direction[0]*34,origin[1]+direction[1]*34];drawArrow(origin,end,color);ctx.fillStyle=color;ctx.fillText(label,end[0]+4,end[1]+4)}}ctx.restore()}}
function drawEnvironment(){{if(view!=='iso')return;const horizon=scene.height*0.68;const sky=ctx.createLinearGradient(0,0,0,horizon);sky.addColorStop(0,'#101f35');sky.addColorStop(1,'#38546b');ctx.fillStyle=sky;ctx.fillRect(0,0,scene.width,horizon);const ground=ctx.createLinearGradient(0,horizon,0,scene.height);ground.addColorStop(0,'#263b3c');ground.addColorStop(1,'#0c1719');ctx.fillStyle=ground;ctx.fillRect(0,horizon,scene.width,scene.height-horizon);ctx.strokeStyle='#78909c';ctx.globalAlpha=.55;ctx.beginPath();ctx.moveTo(0,horizon);ctx.lineTo(scene.width,horizon);ctx.stroke();ctx.globalAlpha=1;const bounds=worldBounds||{{minN:-10,maxN:10,minE:-10,maxE:10}};const span=Math.max(bounds.maxN-bounds.minN,bounds.maxE-bounds.minE,10),margin=Math.max(8,span*.35),minN=bounds.minN-margin,maxN=bounds.maxN+margin,minE=bounds.minE-margin,maxE=bounds.maxE+margin;const step=Math.max(1,Math.ceil(span/6));ctx.save();ctx.beginPath();ctx.rect(0,horizon,scene.width,scene.height-horizon);ctx.clip();ctx.lineWidth=1;for(let n=Math.ceil(minN/step)*step;n<=maxN+.001;n+=step){{const a=project([n,minE,0]),b=project([n,maxE,0]);if(a&&b){{ctx.strokeStyle='#78979a';ctx.globalAlpha=.22;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()}}}}for(let e=Math.ceil(minE/step)*step;e<=maxE+.001;e+=step){{const a=project([minN,e,0]),b=project([maxN,e,0]);if(a&&b){{ctx.strokeStyle='#78979a';ctx.globalAlpha=.22;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()}}}}ctx.restore();}}
function drawAltitudeDrop(point,color){{if(!point||view!=='iso'||Math.abs(point[2])<.05)return;const ground=project([point[0],point[1],0]),top=project(point);if(!ground||!top)return;ctx.save();ctx.strokeStyle=color;ctx.globalAlpha=.55;ctx.setLineDash([3,5]);ctx.beginPath();ctx.moveTo(top[0],top[1]);ctx.lineTo(ground[0],ground[1]);ctx.stroke();ctx.restore()}}
function drawDroneGlyph(point,sample){{if(!point||!sample.vehicle_ned)return;const forward=quatRotate(sample.vehicle_quaternion,[1,0,0]);if(!forward)return;const length=Math.max(.6,14/sceneScale),nose=project([sample.vehicle_ned[0]+forward[0]*length,sample.vehicle_ned[1]+forward[1]*length,sample.vehicle_ned[2]+forward[2]*length]);if(nose){{ctx.save();ctx.globalAlpha=.9;drawArrow(point,nose,'#b9e4ff');ctx.restore()}}}}
function quatRotate(q,v){{if(!q||q.length!==4)return null;let[w,x,y,z]=q;const norm=Math.hypot(w,x,y,z);if(!Number.isFinite(norm)||norm<1e-9)return null;w/=norm;x/=norm;y/=norm;z/=norm;return[(1-2*(y*y+z*z))*v[0]+2*(x*y+w*z)*v[1]+2*(x*z-w*y)*v[2],2*(x*y-w*z)*v[0]+(1-2*(x*x+z*z))*v[1]+2*(y*z+w*x)*v[2],2*(x*z+w*y)*v[0]+2*(y*z-w*x)*v[1]+(1-2*(x*x+y*y))*v[2]]}}
function frame(){{fitScene();ctx.clearRect(0,0,scene.width,scene.height);if(view==='iso')drawEnvironment();else{{ctx.fillStyle='#0b1117';ctx.fillRect(0,0,scene.width,scene.height);ctx.strokeStyle='#243441';ctx.lineWidth=1;for(let x=sceneOrigin[0]%50;x<scene.width;x+=50){{ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,scene.height);ctx.stroke()}}for(let y=sceneOrigin[1]%50;y<scene.height;y+=50){{ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(scene.width,y);ctx.stroke()}}}}ctx.fillStyle='#b6c7d5';ctx.font='600 13px system-ui,sans-serif';const labels={{iso:'3D orbit · N/E/D',top:'Top · North/East',front:'Front · North/Down',side:'Side · East/Down'}};ctx.fillText(labels[view]||view,14,22);if(view==='iso'){{ctx.fillStyle='#8ca2b2';ctx.fillText('Drag to orbit · scroll to zoom',14,41);drawAxisTriad()}}if(document.getElementById('targetHistory').checked)path('target_ned','#ffbd69');if(document.getElementById('droneHistory').checked)path('vehicle_ned','#68b5ff');const s=samples[i];if(!s)return;const drone=project(s.vehicle_ned),target=project(s.target_ned);if(document.getElementById('losToggle').checked&&drone&&target){{ctx.save();ctx.globalAlpha=.8;ctx.setLineDash([4,4]);ctx.strokeStyle='#f2e2a2';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(drone[0],drone[1]);ctx.lineTo(target[0],target[1]);ctx.stroke();ctx.restore()}}if(target){{drawAltitudeDrop(s.target_ned,'#ffbd69');marker(target,'#ffbd69','Target','circle')}}if(drone){{drawAltitudeDrop(s.vehicle_ned,'#68b5ff');marker(drone,'#68b5ff','PX4','diamond');drawDroneGlyph(drone,s)}}if(document.getElementById('commandToggle').checked&&drone&&s.command){{const body=[Number(s.command.vel_body_fwd||0),Number(s.command.vel_body_right||0),Number(s.command.vel_body_down||0)],ned=quatRotate(s.vehicle_quaternion,body);if(ned){{const seconds=2,end=project([s.vehicle_ned[0]+ned[0]*seconds,s.vehicle_ned[1]+ned[1]*seconds,s.vehicle_ned[2]+ned[2]*seconds]);drawArrow(drone,end,'#ff6b6b');ctx.fillStyle='#ffb0b0';ctx.font='12px system-ui,sans-serif';ctx.fillText('intent',end[0]+6,end[1]+14)}}else{{ctx.fillStyle='#ffb0b0';ctx.font='12px system-ui,sans-serif';ctx.fillText('intent: body FRD (attitude unavailable)',14,scene.height-16)}}}}if(s.stale){{ctx.fillStyle='#ffd38d';ctx.font='600 13px system-ui,sans-serif';ctx.fillText('CURRENT SAMPLE STALE / UNKNOWN',scene.width-245,22)}}}}
function timelineDraw(){{tctx.clearRect(0,0,timeline.width,timeline.height);tctx.strokeStyle='#3b4b5b';tctx.strokeRect(0,0,timeline.width,timeline.height);if(!samples.length)return;const min=samples[0].timestamp,max=samples.at(-1).timestamp||min;const x=t=>((t-min)/Math.max(.001,max-min))*timeline.width;const y=(v,minv,maxv)=>timeline.height-20-((v-minv)/(maxv-minv))*140;for(const [key,color] of [['vel_body_fwd','#68b5ff'],['vel_body_right','#ffbd69'],['vel_body_down','#6ee7a1']]){{tctx.strokeStyle=color;tctx.beginPath();let started=false;for(const s of samples){{if(!(key in (s.command||{{}}))){{started=false;continue}}const q=[x(s.timestamp),y(s.command[key],-6,6)];if(!started){{tctx.moveTo(q[0],q[1]);started=true}}else tctx.lineTo(q[0],q[1])}}tctx.stroke()}}tctx.strokeStyle='#ff6b6b';tctx.beginPath();tctx.moveTo(x(samples[i].timestamp),0);tctx.lineTo(x(samples[i].timestamp),timeline.height);tctx.stroke()}}
function update(){{const s=samples[i];document.getElementById('scrub').value=i;document.getElementById('time').textContent=s?`t=${{s.timestamp.toFixed(3)}} · ${{s.stale?'unknown/stale':'fresh evidence'}}`:'';document.getElementById('badges').innerHTML=s?[`<span class="badge">${{s.tracker_state||'state unknown'}}</span>`,`<span class="badge">${{s.continuity_state||'continuity unknown'}}</span>`,...(s.events||[]).map(e=>`<span class="badge warning">${{e}}</span>`)].join(''):'';const range=s?.target_ned&&s?.vehicle_ned?Math.hypot(...s.target_ned.map((value,index)=>value-s.vehicle_ned[index])):null;document.getElementById('values').innerHTML=s?Object.entries({{'target range':range===null?'—':`${{range.toFixed(2)}} m`,'requested speed':s.requested_speed??'—','effective speed':s.effective_speed?.toFixed?.(3)??'—','forward':s.command?.vel_body_fwd?.toFixed?.(3)??'—','right':s.command?.vel_body_right?.toFixed?.(3)??'—','down':s.command?.vel_body_down?.toFixed?.(3)??'—','yaw rate':s.command?.yawspeed_deg_s?.toFixed?.(3)??'—','limiting reason':s.limiting_reason||'—'}}).map(([k,v])=>`<tr><td>${{k}}</td><td>${{v}}</td></tr>`).join(''):'';frame();timelineDraw()}}
document.getElementById('play').onclick=()=>{{playing=!playing;document.getElementById('play').textContent=playing?'Pause':'Play';if(playing)tick()}};function tick(){{if(!playing)return;i=Math.min(samples.length-1,i+1);update();timer=setTimeout(tick,50/Number(document.getElementById('rate').value))}}document.getElementById('reset').onclick=()=>{{playing=false;i=0;document.getElementById('play').textContent='Play';update()}};document.getElementById('resetView').onclick=()=>{{orbitYaw=-0.65;orbitPitch=1.32;autoScale=true;view='iso';update()}};document.getElementById('scrub').oninput=e=>{{i=Number(e.target.value);update()}};document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{{view=b.dataset.view;autoScale=true;update()}});['targetHistory','droneHistory','losToggle','commandToggle'].forEach(id=>document.getElementById(id).oninput=update);let dragging=false,lastX=0,lastY=0;scene.addEventListener('pointerdown',event=>{{if(view!=='iso')return;dragging=true;lastX=event.clientX;lastY=event.clientY;scene.setPointerCapture(event.pointerId);event.preventDefault()}});scene.addEventListener('pointermove',event=>{{if(!dragging)return;orbitYaw+=(event.clientX-lastX)*0.01;orbitPitch=Math.max(-1.45,Math.min(1.45,orbitPitch+(event.clientY-lastY)*0.01));lastX=event.clientX;lastY=event.clientY;update();event.preventDefault()}});scene.addEventListener('pointerup',event=>{{dragging=false;scene.releasePointerCapture?.(event.pointerId)}});scene.addEventListener('pointercancel',()=>{{dragging=false}});scene.addEventListener('wheel',event=>{{if(view!=='iso')return;const factor=event.deltaY<0?1.08:0.93;autoScale=false;sceneScale=Math.max(8,Math.min(100,sceneScale*factor));event.preventDefault();frame() }},{{passive:false}});update();</script></body></html>'''


def write_png(path: Path, scenario: VisualizationScenario, samples: list[VisualizationSample]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    figure, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True)
    times = [sample.timestamp for sample in samples]
    for key, color in (("vel_body_fwd", "#2584c4"), ("vel_body_right", "#d18b24"), ("vel_body_down", "#3a9d62")):
        axes[0].plot(times, [sample.command.get(key, math.nan) for sample in samples], label=key, color=color)
    axes[0].set_title(f"{scenario.name}: command intent (PX4 pose is separate evidence)")
    axes[0].set_ylabel("m/s")
    axes[0].legend()
    target = [sample.target_ned for sample in samples]
    vehicle = [sample.vehicle_ned for sample in samples]
    if any(target):
        axes[1].plot([point[0] for point in target if point], [point[1] for point in target if point], label="target truth", color="#d18b24")
    if any(vehicle):
        axes[1].plot([point[0] for point in vehicle if point], [point[1] for point in vehicle if point], label="PX4-observed pose", color="#2584c4")
    axes[1].set_xlabel("north (m)")
    axes[1].set_ylabel("east (m)")
    if any(target) or any(vehicle):
        axes[1].legend()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def poll_live_pose(url: str, system_id: int, duration_s: float, token: str | None, output: Path, interval_s: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.monotonic()
    with output.open("w", encoding="utf-8") as stream:
        while time.monotonic() - started < duration_s:
            request = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(request, timeout=max(2.0, interval_s * 4.0)) as response:
                    snapshot = json.loads(response.read().decode("utf-8"))
                position, quaternion = pose_from_mavlink2rest(snapshot, system_id)
                record = {
                    "timestamp": dt.datetime.now(dt.timezone.utc).timestamp(),
                    "vehicle_ned": position,
                    "vehicle_quaternion": quaternion,
                    "source": "read_only_mavlink2rest",
                }
                stream.write(json.dumps(record) + "\n")
                stream.flush()
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                stream.write(json.dumps({"timestamp": dt.datetime.now(dt.timezone.utc).timestamp(), "error": str(exc)}) + "\n")
                stream.flush()
            time.sleep(interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--live-url")
    parser.add_argument("--system-id", type=int, default=1)
    parser.add_argument("--duration-s", type=float, default=30.0)
    parser.add_argument("--interval-s", type=float, default=0.1)
    parser.add_argument("--token")
    args = parser.parse_args()
    if not args.evidence_root and not args.live_url:
        parser.error("one of --evidence-root or --live-url is required")
    scenario = VisualizationScenario.from_yaml(args.scenario)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    evidence_root = args.evidence_root or output / "evidence"
    if args.live_url:
        poll_live_pose(args.live_url, args.system_id, args.duration_s, args.token, evidence_root / "px4" / "pose_trace.jsonl", args.interval_s)
    evidence = load_evidence(evidence_root)
    samples = build_timeline(scenario, evidence)
    summary = analyze_timeline(scenario, samples)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "trace.json").write_text(json.dumps([sample.to_dict() for sample in samples], indent=2) + "\n", encoding="utf-8")
    write_csv(output / "trace.csv", samples)
    (output / "index.html").write_text(build_html(scenario, samples, summary), encoding="utf-8")
    write_png(output / "summary.png", scenario, samples)
    print(f"Wrote read-only SIH visualization to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
