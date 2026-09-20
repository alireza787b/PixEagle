// Authorized standalone-camera test. Following must remain off; no flight actions.
const {chromium}=require('../../dashboard/node_modules/playwright');
const fs=require('fs');const assert=require('assert');const events=[];
const record=(kind,data)=>{events.push({time:Date.now()/1000,kind,data});fs.writeFileSync(__dirname+'/browser-hold-events.json',JSON.stringify(events,null,2));};
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome'});const page=await browser.newPage({viewport:{width:1280,height:1000}});
const status=async()=>{const d=await(await page.request.get('http://127.0.0.1:5077/api/v1/gimbal/control')).json();record('status',d);return d;};
const stop=async()=>{const r=await page.request.post('http://127.0.0.1:5077/api/v1/actions/gimbal-control',{data:{operation:'stop',confirm:true,source:'dashboard',reason:'horizontal_hold_acceptance_cleanup',idempotency_key:'hold-cleanup-'+Date.now()}});record('stop_response',await r.json());};
page.on('pageerror',e=>record('pageerror',e.message));page.on('request',r=>{if(r.url().endsWith('/actions/gimbal-control'))record('request',r.postDataJSON());});page.on('response',async r=>{if(r.url().endsWith('/actions/gimbal-control'))record('response',await r.json());});
try{const s=await status();assert(s.available&&s.connected&&!s.following_active&&s.tracking_state==='disabled');
await page.goto('http://127.0.0.1:3040');await page.getByRole('combobox',{name:'Movement',exact:true}).selectOption('fine');
for(const name of ['Pan right','Pan left']){const button=page.getByRole('button',{name,exact:true});await button.waitFor();await button.scrollIntoViewIfNeeded();const r=await button.boundingBox();record('hold_start',{name});await page.mouse.move(r.x+r.width/2,r.y+r.height/2);await page.mouse.down();await page.waitForTimeout(650);await page.mouse.up();record('release',{name});await page.waitForTimeout(900);await status();}
await page.screenshot({path:__dirname+'/browser-hold.png'});}
finally{await stop();await browser.close();}})().catch(e=>{record('error',String(e.stack));console.error(e);process.exitCode=1});
