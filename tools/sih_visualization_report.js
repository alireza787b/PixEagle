// Embedded in the standalone, read-only SIH report. No control or network actions.
let i=0,playing=false,view='iso',timer=null;
const scene=document.getElementById('scene'),ctx=scene.getContext('2d'),timeline=document.getElementById('timeline'),tctx=timeline.getContext('2d');
const samples=PAYLOAD.samples||[];
const firstControlSample = samples.find(s => Number.isFinite(s.requested_speed));
const firstRequest = firstControlSample?.requested_speed;
const requestBasis = contract => contract === 'fixed_wing_external' ? 'session EAS request'
    : contract === 'velocity_body_offboard' || contract === 'gimbal_velocity_body' ? 'session 3D request' : 'session request';
const speedLabel = PAYLOAD.scenario.requested_speed != null ? `Initial request: ${PAYLOAD.scenario.requested_speed} m/s`
    : firstRequest != null ? `Initial ${requestBasis(firstControlSample.command_contract)}: ${firstRequest.toFixed(2)} m/s`
    : PAYLOAD.summary.speed_reference_m_s != null ? `Ceiling: ${PAYLOAD.summary.speed_reference_m_s} m/s` : 'No session speed';
document.getElementById('scenario').textContent=`Purpose: ${PAYLOAD.scenario.follower_purpose} · Follower: ${PAYLOAD.scenario.follower_profile} · Airframe: ${PAYLOAD.scenario.airframe} · Input: ${PAYLOAD.scenario.input_contract} · Command: ${PAYLOAD.scenario.command_contract} · Speed policy: ${PAYLOAD.scenario.speed_source_policy} · Mount: ${PAYLOAD.scenario.mount_type} · Altitude: ${PAYLOAD.scenario.altitude_control?'on':'off'} · ${speedLabel}`;
document.getElementById('summary').textContent=JSON.stringify(PAYLOAD.summary,null,2);
const coverage=document.getElementById('coverage'),evidenceKind=document.getElementById('evidenceKind');
const synthetic=PAYLOAD.summary.evidence_kind==='synthetic_fixture',px4Sih=PAYLOAD.summary.evidence_kind==='px4_sih';
const px4Gazebo=PAYLOAD.summary.evidence_kind==='px4_gazebo';
const alignedPoseCount=Number(PAYLOAD.summary.pose_observed_samples||0),rawPoseCount=PAYLOAD.summary.evidence_counts?.pose;
const hasRawPoseCount=!synthetic&&Number.isInteger(rawPoseCount)&&rawPoseCount>=0;
const poseCount=hasRawPoseCount?rawPoseCount:alignedPoseCount;
evidenceKind.textContent=synthetic?'Synthetic moving-target fixture':px4Sih?'PX4-observed SIH · component':px4Gazebo?'PX4-observed Gazebo':'Imported trace · read-only';
coverage.textContent=synthetic?`Synthetic pose: ${poseCount} samples`:hasRawPoseCount?`${px4Sih||px4Gazebo?'PX4 pose':'Pose'}: ${poseCount} records`:`Aligned pose samples: ${poseCount}`;
if(!poseCount||synthetic)coverage.classList.add('warning');
document.getElementById('scrub').max=Math.max(0,samples.length-1);
const motion=PAYLOAD.summary.motion_summary||{},range=PAYLOAD.summary.target_range_m||{};
const poseBasis=synthetic?'synthetic vehicle pose':px4Sih||px4Gazebo?'PX4-observed pose':'imported pose trace';
document.getElementById('motionSummary').textContent=range.start==null||range.end==null ? poseBasis
    : `Start range: ${range.start.toFixed(2)} m · End range: ${range.end.toFixed(2)} m · Change: ${(range.end-range.start).toFixed(2)} m · ${poseBasis}`;
function points(key){return samples.slice(0,i+1).map(s=>s[key]||null)}
let orbitYaw=-0.65,orbitPitch=1.32,sceneScale=35,sceneOrigin=[scene.width/2,scene.height/2],autoScale=true,worldBounds=null;
function oriented(p){if(!p)return null;const n=p[0],e=p[1],d=p[2];if(view!=='iso')return[n,e,d];const yawX=Math.cos(orbitYaw)*n-Math.sin(orbitYaw)*e;const depth=Math.sin(orbitYaw)*n+Math.cos(orbitYaw)*e;const pitchY=Math.cos(orbitPitch)*depth+Math.sin(orbitPitch)*d;const pitchDepth=-Math.sin(orbitPitch)*depth+Math.cos(orbitPitch)*d;return[yawX,pitchY,pitchDepth]}
function projected(p){if(!p)return null;const o=oriented(p);if(view==='front')return[o[1],o[2]];if(view==='side')return[o[0],o[2]];return[o[0],o[1]]}
function fitScene(){if(!autoScale)return;const all=[];for(const s of samples){if(s.target_ned)all.push(s.target_ned);if(s.vehicle_ned)all.push(s.vehicle_ned)}if(!all.length){sceneScale=35;sceneOrigin=[scene.width/2,scene.height/2];worldBounds=null;return}worldBounds={minN:Math.min(...all.map(p=>p[0])),maxN:Math.max(...all.map(p=>p[0])),minE:Math.min(...all.map(p=>p[1])),maxE:Math.max(...all.map(p=>p[1])),minD:Math.min(...all.map(p=>p[2])),maxD:Math.max(...all.map(p=>p[2]))};const xy=all.map(projected);const minX=Math.min(...xy.map(p=>p[0])),maxX=Math.max(...xy.map(p=>p[0])),minY=Math.min(...xy.map(p=>p[1])),maxY=Math.max(...xy.map(p=>p[1]));const spanX=Math.max(1,maxX-minX),spanY=Math.max(1,maxY-minY);sceneScale=Math.max(.01,Math.min(55,(scene.width-120)/spanX,(scene.height-120)/spanY));sceneOrigin=[scene.width/2-(minX+maxX)*sceneScale/2,scene.height/2-(minY+maxY)*sceneScale/2]}
function project(p){const q=projected(p);return q?[sceneOrigin[0]+q[0]*sceneScale,sceneOrigin[1]+q[1]*sceneScale]:null}
function drawArrow(a,b,color){if(!a||!b)return;ctx.strokeStyle=color;ctx.fillStyle=color;ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();const ang=Math.atan2(b[1]-a[1],b[0]-a[0]);ctx.beginPath();ctx.moveTo(b[0],b[1]);ctx.lineTo(b[0]-12*Math.cos(ang-.5),b[1]-12*Math.sin(ang-.5));ctx.lineTo(b[0]-12*Math.cos(ang+.5),b[1]-12*Math.sin(ang+.5));ctx.closePath();ctx.fill()}
function path(key,color){const opacity=.38;const ps=points(key).map(project);ctx.save();ctx.globalAlpha=opacity;ctx.strokeStyle=color;ctx.lineWidth=2;ctx.setLineDash([8,6]);ctx.beginPath();let started=false;for(const p of ps){if(!p){started=false;continue}if(!started){ctx.moveTo(p[0],p[1]);started=true}else ctx.lineTo(p[0],p[1])}ctx.stroke();ctx.restore()}
function marker(point,color,label,shape){if(!point)return;ctx.save();ctx.fillStyle=color;ctx.strokeStyle='#071016';ctx.lineWidth=2;ctx.beginPath();if(shape==='diamond'){ctx.moveTo(point[0],point[1]-10);ctx.lineTo(point[0]+10,point[1]);ctx.lineTo(point[0],point[1]+10);ctx.lineTo(point[0]-10,point[1]);ctx.closePath()}else{ctx.arc(point[0],point[1],9,0,Math.PI*2)}ctx.fill();ctx.stroke();ctx.font='600 12px system-ui,sans-serif';ctx.fillStyle='#eef4f8';ctx.fillText(label,point[0]+12,point[1]-10);ctx.restore()}
function drawAxisTriad(){if(view!=='iso')return;const origin=[70,scene.height-64];const axes=[['N',[1,0,0],'#d9efff'],['E',[0,1,0],'#ffbd69'],['D',[0,0,1],'#6ee7a1']];ctx.save();ctx.font='600 12px system-ui,sans-serif';for(const[label,vector,color]of axes){const direction=projected(vector),end=[origin[0]+direction[0]*34,origin[1]+direction[1]*34];drawArrow(origin,end,color);ctx.fillStyle=color;ctx.fillText(label,end[0]+4,end[1]+4)}ctx.restore()}
function drawEnvironment(){if(view!=='iso')return;const horizon=scene.height*0.68;const sky=ctx.createLinearGradient(0,0,0,horizon);sky.addColorStop(0,'#101f35');sky.addColorStop(1,'#38546b');ctx.fillStyle=sky;ctx.fillRect(0,0,scene.width,horizon);const ground=ctx.createLinearGradient(0,horizon,0,scene.height);ground.addColorStop(0,'#263b3c');ground.addColorStop(1,'#0c1719');ctx.fillStyle=ground;ctx.fillRect(0,horizon,scene.width,scene.height-horizon);ctx.strokeStyle='#78909c';ctx.globalAlpha=.55;ctx.beginPath();ctx.moveTo(0,horizon);ctx.lineTo(scene.width,horizon);ctx.stroke();ctx.globalAlpha=1;const bounds=worldBounds||{minN:-10,maxN:10,minE:-10,maxE:10};const span=Math.max(bounds.maxN-bounds.minN,bounds.maxE-bounds.minE,10),margin=Math.max(8,span*.35),minN=bounds.minN-margin,maxN=bounds.maxN+margin,minE=bounds.minE-margin,maxE=bounds.maxE+margin;const step=Math.max(1,Math.ceil(span/6));ctx.save();ctx.beginPath();ctx.rect(0,horizon,scene.width,scene.height-horizon);ctx.clip();ctx.lineWidth=1;for(let n=Math.ceil(minN/step)*step;n<=maxN+.001;n+=step){const a=project([n,minE,0]),b=project([n,maxE,0]);if(a&&b){ctx.strokeStyle='#78979a';ctx.globalAlpha=.22;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()}}for(let e=Math.ceil(minE/step)*step;e<=maxE+.001;e+=step){const a=project([minN,e,0]),b=project([maxN,e,0]);if(a&&b){ctx.strokeStyle='#78979a';ctx.globalAlpha=.22;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke()}}ctx.restore();}
function drawAltitudeDrop(point,color){if(!point||view!=='iso'||Math.abs(point[2])<.05)return;const ground=project([point[0],point[1],0]),top=project(point);if(!ground||!top)return;ctx.save();ctx.strokeStyle=color;ctx.globalAlpha=.55;ctx.setLineDash([3,5]);ctx.beginPath();ctx.moveTo(top[0],top[1]);ctx.lineTo(ground[0],ground[1]);ctx.stroke();ctx.restore()}
function drawDroneGlyph(point,sample){if(!point||!sample.vehicle_ned)return;const forward=sample.vehicle_forward_ned;if(!forward)return;const length=Math.max(.6,14/sceneScale),nose=project([sample.vehicle_ned[0]+forward[0]*length,sample.vehicle_ned[1]+forward[1]*length,sample.vehicle_ned[2]+forward[2]*length]);if(nose){ctx.save();ctx.globalAlpha=.9;drawArrow(point,nose,'#b9e4ff');ctx.restore()}}
function frame(){fitScene();ctx.clearRect(0,0,scene.width,scene.height);if(view==='iso')drawEnvironment();else{ctx.fillStyle='#0b1117';ctx.fillRect(0,0,scene.width,scene.height);ctx.strokeStyle='#243441';ctx.lineWidth=1;for(let x=sceneOrigin[0]%50;x<scene.width;x+=50){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,scene.height);ctx.stroke()}for(let y=sceneOrigin[1]%50;y<scene.height;y+=50){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(scene.width,y);ctx.stroke()}}ctx.fillStyle='#b6c7d5';ctx.font='600 13px system-ui,sans-serif';const labels={iso:'3D orbit · N/E/D',top:'Top · North/East',front:'Front · East/Down',side:'Side · North/Down'};ctx.fillText(labels[view]||view,14,22);if(view==='iso'){ctx.fillStyle='#8ca2b2';ctx.fillText('Drag to orbit · scroll to zoom',14,41);drawAxisTriad()}if(document.getElementById('targetHistory').checked)path('target_ned','#ffbd69');if(document.getElementById('droneHistory').checked)path('vehicle_ned','#68b5ff');const s=samples[i];if(!s)return;const drone=project(s.vehicle_ned),target=project(s.target_ned);if(document.getElementById('losToggle').checked&&drone&&target){ctx.save();ctx.globalAlpha=.8;ctx.setLineDash([4,4]);ctx.strokeStyle='#f2e2a2';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(drone[0],drone[1]);ctx.lineTo(target[0],target[1]);ctx.stroke();ctx.restore()}if(target){drawAltitudeDrop(s.target_ned,'#ffbd69');marker(target,'#ffbd69','Target','circle')}if(drone){drawAltitudeDrop(s.vehicle_ned,'#68b5ff');marker(drone,'#68b5ff',synthetic?'Fixture':'PX4','diamond');drawDroneGlyph(drone,s)}if(document.getElementById('commandToggle').checked&&drone&&s.command)drawCommand(drone,s);if(s.stale){ctx.fillStyle='#ffd38d';ctx.font='600 13px system-ui,sans-serif';ctx.fillText('CURRENT SAMPLE STALE / UNKNOWN',scene.width-245,22)}}
function commandRows(sample) {
    const c = sample.command || {};
    const unit = (v, suffix, digits = 2) => Number.isFinite(v) ? `${v.toFixed(digits)} ${suffix}` : '—';
    if (['fixed_wing_external', 'vtol_transition_external'].includes(sample.command_contract)) {
        const rows = {
            'course request': unit(Number.isFinite(c.course_rad) ? c.course_rad * 180 / Math.PI : null, '°'),
            'EAS request': unit(c.equivalent_airspeed_m_s, 'm/s'),
            'native EAS reference': unit(sample.native_effective_eas_m_s, 'm/s'),
            'observed EAS': unit(sample.observed_eas_m_s, 'm/s'),
        };
        if ('altitude_amsl_m' in c) rows['altitude hold (AMSL)'] = unit(c.altitude_amsl_m, 'm');
        if ('height_rate_m_s' in c) rows['height rate (up +)'] = unit(c.height_rate_m_s, 'm/s');
        return rows;
    }
    if (sample.command_contract === 'attitude_rate') return {
        'roll rate': unit(c.rollspeed_deg_s, '°/s'), 'pitch rate': unit(c.pitchspeed_deg_s, '°/s'),
        'yaw rate': unit(c.yawspeed_deg_s, '°/s'), 'thrust': unit(c.thrust, '', 3),
    };
    if (sample.command_contract === 'velocity_body_offboard') return {
        'command source': ({submitted: 'Submitted fields', published_intent: 'Published intent',
                            proposal: 'Follower proposal'})[sample.command_source] || '—',
        'forward': unit(c.vel_body_fwd, 'm/s'), 'right': unit(c.vel_body_right, 'm/s'),
        'down': unit(c.vel_body_down, 'm/s'), 'yaw rate': unit(c.yawspeed_deg_s, '°/s'),
        'command 3D speed': unit(sample.effective_speed, 'm/s'),
    };
    return {'command contract': 'unknown'};
}
function drawCommand(drone, sample) {
    const c = sample.command || {};
    if (sample.command_contract === 'attitude_rate') {
        ctx.fillStyle = '#c49cff'; ctx.font = '600 12px system-ui,sans-serif';
        ctx.fillText('Rate / thrust intent · see current sample', 14, scene.height - 16);
        return;
    }
    const native = ['fixed_wing_external', 'vtol_transition_external'].includes(sample.command_contract);
    const ned = native ? sample.course_direction_ned : sample.command_ned;
    if (ned) {
        const length = native ? Math.max(1, 65 / sceneScale) : 2;
        const end = project(sample.vehicle_ned.map((v, k) => v + ned[k] * length));
        drawArrow(drone, end, '#ff6b6b'); ctx.fillStyle = '#ffb0b0'; ctx.font = '12px system-ui,sans-serif';
        ctx.fillText(native ? 'course intent' : 'velocity intent', end[0] + 6, end[1] + 14);
    } else {
        ctx.fillStyle = '#ffb0b0'; ctx.font = '12px system-ui,sans-serif';
        ctx.fillText('Intent direction unavailable', 14, scene.height - 16);
    }
}
const horizontalSpeed = ned => ned ? Math.hypot(ned[0], ned[1]) : null;
const series = [
    ['requested speed (m/s)', s => s.requested_speed, '#ffbd69'],
    ['forward (m/s)', s => s.command.vel_body_fwd, '#68b5ff'],
    ['right (m/s)', s => s.command.vel_body_right, '#ffbd69'],
    ['command down (m/s)', s => s.command.vel_body_down, '#6ee7a1'],
    ['PX4 horiz. setpoint (m/s)', s => horizontalSpeed(s.px4_velocity_setpoint_ned), '#e28fff'],
    ['ground speed (m/s)', s => horizontalSpeed(s.vehicle_velocity_ned), '#68b5ff'],
    ['PX4 down setpoint (m/s)', s => s.px4_velocity_setpoint_ned?.[2], '#e28fff'],
    ['observed down (m/s)', s => s.vehicle_velocity_ned?.[2], '#68b5ff'],
    ['local altitude (m)', s => s.vehicle_ned ? -s.vehicle_ned[2] : null, '#6ee7a1'],
    ['yaw rate (°/s)', s => s.command.yawspeed_deg_s, '#c49cff'],
    ['roll rate (°/s)', s => s.command.rollspeed_deg_s, '#68b5ff'],
    ['pitch rate (°/s)', s => s.command.pitchspeed_deg_s, '#ffbd69'],
    ['thrust', s => s.command.thrust, '#6ee7a1'],
    ['course (°)', s => Number.isFinite(s.command.course_rad) ? s.command.course_rad * 180 / Math.PI : null, '#ff6b6b'],
    ['EAS request (m/s)', s => s.command.equivalent_airspeed_m_s, '#68b5ff'],
    ['native EAS (m/s)', s => s.native_effective_eas_m_s, '#6ee7a1'],
    ['observed EAS (m/s)', s => s.observed_eas_m_s, '#ffbd69'],
    ['height rate (m/s)', s => s.command.height_rate_m_s, '#c49cff'],
    ['AMSL hold (m)', s => s.command.altitude_amsl_m, '#6ee7a1'],
].filter(([, value]) => samples.some(s => Number.isFinite(value(s))));
function timelineDraw() {
    const height = Math.max(120, series.length * 48);
    timeline.width = Math.max(320, timeline.clientWidth);
    timeline.height = height; timeline.style.height = `${height}px`;
    tctx.clearRect(0, 0, timeline.width, height);
    if (!samples.length) return;
    const start = samples[0].timestamp, end = samples.at(-1).timestamp;
    const left = 145, width = timeline.width - left - 8;
    const x = t => left + (t - start) / Math.max(.001, end - start) * width;
    series.forEach(([label, value, color], row) => {
        const values = samples.map(value).filter(Number.isFinite);
        const low = Math.min(...values), high = Math.max(...values), span = Math.max(high - low, .1);
        const top = row * 48 + 5, bottom = top + 32;
        const y = v => bottom - (v - low + span * .1) / (span * 1.2) * 30;
        tctx.fillStyle = color; tctx.font = '12px system-ui,sans-serif'; tctx.fillText(label, 5, top + 12);
        tctx.fillStyle = '#98a8b7'; tctx.font = '10px system-ui,sans-serif';
        tctx.fillText(`${low.toFixed(1)} … ${high.toFixed(1)}`, 5, top + 27);
        tctx.strokeStyle = '#2d3a47'; tctx.beginPath(); tctx.moveTo(left, bottom + 5); tctx.lineTo(timeline.width, bottom + 5); tctx.stroke();
        tctx.strokeStyle = color; tctx.beginPath(); let previous = null;
        for (const s of samples) {
            const v = value(s);
            if (!Number.isFinite(v)) { previous = null; continue; }
            const contiguous = previous && s.timestamp - previous.timestamp <= Math.max(.5, 2 / PAYLOAD.scenario.rate_hz)
                && !(label === 'course (°)' && Math.abs(v - value(previous)) > 180);
            if (contiguous) tctx.lineTo(x(s.timestamp), y(v)); else tctx.moveTo(x(s.timestamp), y(v));
            previous = s;
        }
        tctx.stroke();
    });
    tctx.strokeStyle = '#ff6b6b'; tctx.beginPath(); tctx.moveTo(x(samples[i].timestamp), 0);
    tctx.lineTo(x(samples[i].timestamp), height); tctx.stroke();
}
function update() {
    const s = samples[i]; document.getElementById('scrub').value = i;
    document.getElementById('time').textContent = s ? `t=${s.timestamp.toFixed(3)} · ${s.stale ? 'unknown/stale' : 'fresh evidence'}` : '';
    const badges = document.getElementById('badges'); badges.replaceChildren();
    if (s) for (const label of [s.aircraft_phase, s.tracker_state, s.continuity_state, ...(s.events || [])].filter(Boolean)) {
        const badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = label; badges.append(badge);
    }
    const range = s?.target_ned && s?.vehicle_ned ? Math.hypot(...s.target_ned.map((v, k) => v - s.vehicle_ned[k])) : null;
    const values = s ? {
        'target range': range === null ? '—' : `${range.toFixed(2)} m`,
        ...(s.speed_source ? {'speed source': s.speed_source} : {'speed policy': PAYLOAD.scenario.speed_source_policy || '—'}),
        'measurement age': s.measurement_age_s == null ? '—' : `${s.measurement_age_s.toFixed(3)} s`,
        [requestBasis(s.command_contract)]: s.requested_speed == null ? '—' : `${s.requested_speed.toFixed(2)} m/s`,
        ...commandRows(s),
        ...(s.px4_velocity_setpoint_ned ? {'PX4 horizontal setpoint': `${horizontalSpeed(s.px4_velocity_setpoint_ned).toFixed(2)} m/s`,
                                          'PX4 down setpoint': `${s.px4_velocity_setpoint_ned[2].toFixed(2)} m/s`} : {}),
        ...(s.vehicle_velocity_ned ? {'observed ground speed': `${horizontalSpeed(s.vehicle_velocity_ned).toFixed(2)} m/s`,
                                      'observed down': `${s.vehicle_velocity_ned[2].toFixed(2)} m/s`} : {}),
        'limiting reason': s.limiting_reason || '—',
    } : {};
    const table = document.getElementById('values'); table.replaceChildren();
    for (const [label, value] of Object.entries(values)) {
        const row = document.createElement('tr');
        for (const text of [label, value]) { const cell = document.createElement('td'); cell.textContent = text; row.append(cell); }
        table.append(row);
    }
    frame(); timelineDraw();
}
document.getElementById('play').onclick = () => {
    playing = !playing && samples.length > 1; clearTimeout(timer);
    document.getElementById('play').textContent = playing ? 'Pause' : 'Play';
    if (playing) { if (i === samples.length - 1) i = 0; tick(); }
};
function tick() {
    if (!playing || i >= samples.length - 1) {
        playing = false; document.getElementById('play').textContent = 'Play'; return;
    }
    const delay = (samples[i + 1].timestamp - samples[i].timestamp) * 1000 / Number(document.getElementById('rate').value);
    timer = setTimeout(() => { if (playing) { i++; update(); tick(); } }, Math.max(1, delay));
}
document.getElementById('reset').onclick=()=>{playing=false;clearTimeout(timer);i=0;document.getElementById('play').textContent='Play';update()};document.getElementById('resetView').onclick=()=>{orbitYaw=-0.65;orbitPitch=1.32;autoScale=true;view='iso';update()};document.getElementById('scrub').oninput=e=>{i=Number(e.target.value);update()};document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{view=b.dataset.view;autoScale=true;update()});['targetHistory','droneHistory','losToggle','commandToggle'].forEach(id=>document.getElementById(id).oninput=update);let dragging=false,lastX=0,lastY=0;scene.addEventListener('pointerdown',event=>{if(view!=='iso')return;dragging=true;lastX=event.clientX;lastY=event.clientY;scene.setPointerCapture(event.pointerId);event.preventDefault()});scene.addEventListener('pointermove',event=>{if(!dragging)return;orbitYaw+=(event.clientX-lastX)*0.01;orbitPitch=Math.max(-1.45,Math.min(1.45,orbitPitch+(event.clientY-lastY)*0.01));lastX=event.clientX;lastY=event.clientY;update();event.preventDefault()});scene.addEventListener('pointerup',event=>{dragging=false;scene.releasePointerCapture?.(event.pointerId)});scene.addEventListener('pointercancel',()=>{dragging=false});scene.addEventListener('wheel',event=>{if(view!=='iso')return;const factor=event.deltaY<0?1.08:0.93;autoScale=false;sceneScale=Math.max(.01,Math.min(100,sceneScale*factor));event.preventDefault();frame() },{passive:false});update();
