#!/usr/bin/env node
/** Browser checks in a disposable context, leaving the user's reader untouched. */
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
const origin=process.env.READER_URL??'http://localhost:5173/';
const debug=process.env.CHROME_DEBUG_URL??'http://127.0.0.1:9222';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function connect(url,onEvent=()=>{}){
 const ws=new WebSocket(url);let sequence=0;const pending=new Map();
 const ready=new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 ws.addEventListener('message',event=>{const m=JSON.parse(String(event.data));if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);if(m.error)p.reject(new Error(m.error.message));else p.resolve(m.result);}else if(m.method)onEvent(m);});
 return{async send(method,params={}){await ready;return new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});},close(){for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('CDP closed'));}pending.clear();ws.close();}};
}
const version=await(await fetch(debug+'/json/version')).json();const browser=connect(version.webSocketDebuggerUrl);const {browserContextId}=await browser.send('Target.createBrowserContext',{disposeOnDetach:true});let page;
const errors=[];
try{
 const {targetId}=await browser.send('Target.createTarget',{url:'about:blank',browserContextId});let target;
 for(let attempt=0;attempt<50;attempt++){target=(await(await fetch(debug+'/json/list')).json()).find(t=>t.id===targetId);if(target?.webSocketDebuggerUrl)break;await delay(100);}
 assert.ok(target?.webSocketDebuggerUrl);page=connect(target.webSocketDebuggerUrl,m=>{if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description??m.params.exceptionDetails.text);if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')errors.push(m.params.args.map(a=>a.value??a.description).join(' '));});
 await page.send('Page.enable');await page.send('Runtime.enable');
 const evaluate=async expression=>{const r=await page.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description??r.exceptionDetails.text);return r.result.value;};
 async function wait(expression,label){for(let attempt=0;attempt<200;attempt++){if(await evaluate(`Boolean(${expression})`))return;await delay(100);}throw new Error(label+'\n'+await evaluate('document.body.innerText.slice(0,2400)'));}
 async function click(expression){await evaluate(`(${expression}).scrollIntoView({block:'center'})`);await delay(180);const r=await evaluate(`(${expression}).getBoundingClientRect().toJSON()`);const x=r.x+r.width/2,y=r.y+r.height/2;await page.send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',clickCount:1});await page.send('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',clickCount:1});await delay(150);}
 await page.send('Page.navigate',{url:origin});await wait("document.querySelectorAll('article').length===8",'eight-paper library');
 for(let n=2;n<=8;n++){
  const pid=`paper-${String(n).padStart(2,'0')}`,paper=JSON.parse(await readFile(new URL(`../public/data/${pid}.json`,import.meta.url),'utf8')),before=JSON.parse(await readFile(new URL(`../content/${pid}-before-remaining-companion.json`,import.meta.url),'utf8'));
  const link=paper.exhibitCompanion.links.find(l=>l.confidence==='high'&&l.exhibitId.includes('-table-'));
  const repair=paper.readingUnitRepairs.find(r=>r.revision==='remaining-papers-companion-v1'&&r.absorbedIds.length);
  const archived=repair.absorbedIds[0],readerKey=`paper-focus-reader:v1:${pid}`;
  const state={version:1,paperId:pid,sourceSha256:paper.sourceSha256,currentSegmentId:link.segmentId,seen:[],understood:[],bookmarks:[archived],notes:{[archived]:'保留原段落筆記'},dimOpacity:.74,reducedMotion:true,highContrast:false,updatedAt:new Date().toISOString()};
  await evaluate(`localStorage.setItem(${JSON.stringify('paper-focus-curator:v1:'+pid)},${JSON.stringify(JSON.stringify(before))});localStorage.setItem(${JSON.stringify(readerKey)},${JSON.stringify(JSON.stringify(state))});`);
  await page.send('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
  await page.send('Page.navigate',{url:origin+'?companion-check='+n});
  await wait("document.querySelectorAll('article').length===8",pid+' library selection');
  await click(`[...document.querySelectorAll('article')][${n-1}].querySelector('button:last-child')`);
  await wait("document.querySelector('.reader-footer')",pid+' reader');
  await wait(`document.querySelector('[data-companion-window="${link.exhibitId}"] img')?.naturalWidth>500`,pid+' complete companion image');
  const captions=new Set(paper.exhibits.map(e=>e.captionSegmentId)),count=paper.segments.filter(s=>!s.excluded&&!s.readingRole&&s.kind!=='caption'&&!captions.has(s.id)).length;
  assert.ok(await evaluate(`document.querySelector('header').innerText.includes('/ ${count}')`),pid+' core-step count');
  const persisted=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)}))`);assert.deepEqual(persisted.notes,state.notes);assert.deepEqual(persisted.bookmarks,state.bookmarks);assert.equal(persisted.currentSegmentId,link.segmentId);
  assert.equal(await evaluate("document.querySelectorAll('[data-supplement-statement]').length"),0);
  if(paper.readingQuality.appendices.length){
   await click("document.querySelector('button[aria-label=\"查看完整附錄\"]')");
   await wait("document.querySelector('[data-complete-appendix] img')?.naturalWidth>1900",'complete content-analysis appendix');
   assert.ok(await evaluate("document.querySelector('[data-appendix-translation]').textContent.includes('A3–11')"));
   await page.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
   await page.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
   await wait("!document.querySelector('[data-paper-supplements]')",'appendix sheet closed');
  }else assert.ok(await evaluate("!document.querySelector('button[aria-label=\"查看完整附錄\"]')"));
  const after=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)}))`);assert.deepEqual(after.notes,state.notes);assert.equal(after.currentSegmentId,link.segmentId);
  await page.send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await delay(300);
  assert.ok(await evaluate("document.documentElement.scrollWidth<=innerWidth+1"),pid+' mobile width');
  await wait(`document.querySelector('[data-companion-window="${link.exhibitId}"] img')?.naturalWidth>500`,pid+' mobile companion');
  if(n===8){const shot=await page.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile('/private/tmp/remaining-papers-mobile.png',Buffer.from(shot.data,'base64'));}
  console.log(pid+': old-draft migration, companion, simplified appendix access, preserved notes and mobile layout passed.');
 }
 assert.deepEqual(errors,[]);console.log('All seven browser checks passed in an isolated context.');
}finally{page?.close();await browser.send('Target.disposeBrowserContext',{browserContextId});browser.close();}
