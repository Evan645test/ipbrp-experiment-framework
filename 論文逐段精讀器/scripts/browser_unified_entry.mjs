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
 await page.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await page.send('Page.navigate',{url:origin+'?entry-check=1'});
 await wait("document.querySelectorAll('article').length===8",'unified library');
 assert.ok(await evaluate("document.querySelector('h1').innerText.includes('從研究全貌')"));
 for(let n=1;n<=8;n++){
  console.log('Checking unified entry '+n);
  const pid=`paper-${String(n).padStart(2,'0')}`;
  const paper=JSON.parse(await readFile(new URL(`../public/data/${pid}.json`,import.meta.url),'utf8'));
  const core=paper.segments.find(s=>!s.excluded&&!s.readingRole&&s.kind==='body');
  const key=`paper-focus-reader:v1:${pid}`;
  const state={version:1,paperId:pid,sourceSha256:paper.sourceSha256,currentSegmentId:core.id,seen:[],understood:[],bookmarks:[core.id],notes:{[core.id]:'切換閱讀方式仍保留筆記'},dimOpacity:.74,reducedMotion:true,highContrast:false,updatedAt:new Date().toISOString()};
  await evaluate(`localStorage.setItem(${JSON.stringify(key)},${JSON.stringify(JSON.stringify(state))})`);
  await click(`[...document.querySelectorAll('article')][${n-1}].querySelector('button[aria-label]')`);
  await wait(`document.querySelector('[data-guide-screen="${pid}"] iframe')?.contentDocument?.querySelector('h1')?.textContent.length>0`,pid+' original guide');
  assert.equal(await evaluate('location.hash'),`#guide:${pid}`);
  if(n===1) assert.ok(await evaluate("['researchGapSection','assignmentSection','readerQuestionsSection'].every(id=>document.querySelector('iframe').contentDocument.getElementById(id))"),'latest first-paper sections');
  await click("document.querySelector('button[aria-label=\"切換至本篇逐段精讀\"]')");
  await wait("document.querySelector('.reader-footer')",pid+' focused reader');
  await wait("document.querySelector('article.pdf-page-stage canvas')?.width>100",pid+' original PDF rendered');
  await wait(`JSON.parse(localStorage.getItem(${JSON.stringify(key)})).currentSegmentId===${JSON.stringify(core.id)}`,pid+' restored position');
  assert.ok(await evaluate("!document.querySelector('button[aria-label*=\"研究聲明\"]')"));
  assert.equal(await evaluate("document.querySelectorAll('[data-supplement-statement]').length"),0);
  if(n===1){
   await click("document.querySelector('button[aria-label=\"查看完整附錄\"]')");
   await wait("document.querySelector('[data-complete-appendix=\"paper-01-appendix-i\"] img')?.naturalWidth>1900",'first complete appendix');
   await click("document.querySelector('[data-appendix-tab=\"paper-01-appendix-ii\"]')");
   await wait("document.querySelector('[data-complete-appendix=\"paper-01-appendix-ii\"] img')?.naturalWidth>1900",'second complete appendix');
   await page.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
   await page.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
   await wait("!document.querySelector('[data-paper-supplements]')",'appendix sheet closed');
  }
  const saved=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(key)}))`);
  assert.deepEqual(saved.notes,state.notes);assert.deepEqual(saved.bookmarks,state.bookmarks);
  await click("document.querySelector('button[aria-label=\"切換至本篇互動導讀\"]')");
  await wait(`document.querySelector('[data-guide-screen="${pid}"] iframe')?.contentDocument?.querySelector('h1')`,pid+' switch back');
  await click("document.querySelector('button[aria-label=\"回到論文書庫\"]')");
  await wait("document.querySelectorAll('article').length===8",'back to unified library');
  if(n===1){
   await evaluate('history.back()');
   await wait("document.querySelector('[data-guide-screen=\"paper-01\"] iframe')?.contentDocument?.querySelector('#readerQuestionsSection')",'browser back to latest guide');
   await evaluate('history.forward()');
   await wait("document.querySelectorAll('article').length===8",'browser forward to library');
  }
  console.log(pid+': original guide and focused reader switch correctly; notes, bookmark and position preserved.');
 }
 await page.send('Page.navigate',{url:origin+'?entry-check=deep#guide:paper-03'});
 await wait("document.querySelector('[data-guide-screen=\"paper-03\"] iframe')?.contentDocument?.querySelector('h1')",'direct guide entry');
 await page.send('Page.reload');
 await delay(700);
 await wait("document.querySelector('[data-guide-screen=\"paper-03\"] iframe')?.contentDocument?.querySelector('h1')",'guide survives reload');
 await click("document.querySelector('button[aria-label=\"下一篇導讀\"]')");
 await wait("document.querySelector('[data-guide-screen=\"paper-04\"] iframe')?.contentDocument?.querySelector('h1')",'next guide');
 await page.send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await delay(300);
 assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'mobile guide width');
 const shot=await page.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 await writeFile('/private/tmp/paper-unified-guide-mobile.png',Buffer.from(shot.data,'base64'));
 await click("document.querySelector('button[aria-label=\"回到論文書庫\"]')");
 await wait("document.querySelectorAll('article').length===8",'mobile unified library');
 assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'mobile library width');
 const libraryShot=await page.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 await writeFile('/private/tmp/paper-unified-library-mobile.png',Buffer.from(libraryShot.data,'base64'));
 assert.deepEqual(errors,[]);console.log('Eight guides, same-paper switches, direct entry, reload and mobile layouts passed.');

}finally{page?.close();try{await browser.send('Target.disposeBrowserContext',{browserContextId});}catch(error){console.error('Browser cleanup: '+error.message);}browser.close();}
