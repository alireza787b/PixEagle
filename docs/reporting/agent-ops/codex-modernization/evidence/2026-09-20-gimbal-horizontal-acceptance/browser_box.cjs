// Operator-authorized Classic rectangle test, at most four seconds, then Cancel + Stop.
const {chromium}=require('../../dashboard/node_modules/playwright');const fs=require('fs');const assert=require('assert');const events=[];
const record=(kind,data)=>{events.push({time:Date.now()/1000,kind,data});fs.writeFileSync(__dirname+'/browser-box-events.json',JSON.stringify(events,null,2));};
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome'});const page=await browser.newPage({viewport:{width:1280,height:1000}});
const status=async()=>{const s=await(await page.request.get('http://127.0.0.1:5077/api/v1/gimbal/control')).json();record('status',s);return s;};
const action=async operation=>{const r=await page.request.post('http://127.0.0.1:5077/api/v1/actions/gimbal-control',{data:{operation,confirm:true,source:'dashboard',reason:'horizontal_rectangle_acceptance_cleanup',idempotency_key:'rectangle-'+operation+'-'+Date.now()}});record('cleanup',await r.json());};
page.on('pageerror',e=>record('pageerror',e.message));page.on('request',r=>{if(r.url().endsWith('/actions/gimbal-control'))record('request',r.postDataJSON());});page.on('response',async r=>{if(r.url().endsWith('/actions/gimbal-control'))record('response',await r.json());});
try{const s=await status();assert(s.available&&s.connected&&!s.following_active&&s.selection_mode==='classic');await page.goto('http://127.0.0.1:3040');await page.getByText('Gimbal camera',{exact:true}).waitFor();await page.getByRole('combobox').nth(1).click();await page.getByRole('option',{name:'WebSocket',exact:true}).click();
await page.waitForFunction(()=>document.querySelector('[data-video-media=true]')?.dataset.frameReady==='true');
const geometry=await page.getByTestId('bounding-box-draw-surface').evaluate(e=>{const r=e.getBoundingClientRect(),v=e.querySelector('[data-video-media=true]');const a=(v.videoWidth||v.naturalWidth||v.width)/(v.videoHeight||v.naturalHeight||v.height);const width=Math.min(r.width,r.height*a),height=width/a;return{x:r.x+(r.width-width)/2,y:r.y+(r.height-height)/2,width,height};});
const box={x:.625,y:.245,width:.075,height:.105};record('rectangle',{box,geometry,subject:'orange pen holder, inspected native image'});await page.screenshot({path:__dirname+'/rectangle-before.png'});
const point=(x,y)=>({x:geometry.x+x*geometry.width,y:geometry.y+y*geometry.height});const a=point(box.x-box.width/2,box.y-box.height/2),b=point(box.x+box.width/2,box.y+box.height/2);
const response=page.waitForResponse(r=>r.url().endsWith('/actions/gimbal-control'));await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:8});await page.mouse.up();const result=await(await response).json();assert.equal(result.status,'success');
for(let i=0;i<16;i++){await page.waitForTimeout(250);const s=await status();if(s.tracking_state==='target_lost'){record('abort','camera reported target lost');break;}}
await page.screenshot({path:__dirname+'/rectangle-after.png'});
}finally{try{await action('cancel');}finally{await action('stop');await browser.close();}}})().catch(e=>{record('error',String(e.stack));console.error(e);process.exitCode=1});
