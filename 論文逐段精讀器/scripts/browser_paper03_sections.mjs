#!/usr/bin/env node
/** Browser checks in a disposable context, leaving the user's reader untouched. */
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
const origin=process.env.READER_URL??'http://127.0.0.1:8765/ipbrp-experiment-framework/';
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

 async function assertPdfFocus(segment){
  await wait(`document.querySelectorAll('article.pdf-page-stage canvas').length===${segment.fragments.length}&&[...document.querySelectorAll('article.pdf-page-stage canvas')].every(c=>c.width>100)`,'PDF paragraph canvases');
  await wait(`(()=>{const stages=[...document.querySelectorAll('article.pdf-page-stage')],fragments=${JSON.stringify(segment.fragments)};return stages.every((stage,i)=>{const frame=stage.querySelector('.ring-amber-400'),canvas=stage.querySelector('canvas'),f=fragments[i];if(!frame)return false;const scale=parseFloat(canvas.style.width)/f.pageSize[0];return Math.abs(parseFloat(frame.style.top)-f.bbox[1]*scale)<.03&&Math.abs(parseFloat(frame.style.height)-(f.bbox[3]-f.bbox[1])*scale)<.03;});})()`,'PDF highlights body rather than companion figure');
 }
 const pid='paper-03',attentionId='paper-03-s-3d80198491e5',beforeId='paper-03-s-89c788a9719e';
 const paper=JSON.parse(await readFile(new URL('../public/data/paper-03.json',import.meta.url),'utf8'));
 const old=structuredClone(paper);delete old.sectionRepairs;
 for(const repair of paper.sectionRepairs)old.segments.find(s=>s.id===repair.segmentId).section=repair.previousSection;
 const readerKey=`paper-focus-reader:v1:${pid}`;
 const state={version:1,paperId:pid,sourceSha256:paper.sourceSha256,currentSegmentId:beforeId,seen:[],understood:[],bookmarks:[attentionId],notes:{[attentionId]:'注意力段落的原有筆記'},dimOpacity:.74,reducedMotion:true,highContrast:false,updatedAt:new Date().toISOString()};
 await page.send('Emulation.setDeviceMetricsOverride',{width:1600,height:1000,deviceScaleFactor:1,mobile:false});
 await page.send('Page.navigate',{url:origin});
 await wait("document.querySelectorAll('article').length===8",'library');
 await evaluate(`localStorage.setItem('paper-focus-curator:v1:paper-03',${JSON.stringify(JSON.stringify(old))});localStorage.setItem(${JSON.stringify(readerKey)},${JSON.stringify(JSON.stringify(state))})`);
 await page.send('Page.navigate',{url:origin+'?attention-check=1#paper-03'});
 await wait("document.querySelector('.reader-footer')",'paper 3 reader');
 await wait(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)})).currentSegmentId===${JSON.stringify(beforeId)}`,'restored preceding paragraph');
 await click("document.querySelector('.reader-footer button:last-child')");
 await wait("document.querySelector('[data-translation-scroll]')?.innerText.includes('3.1 Attention model')",'Attention model restored');
 const attention=paper.segments.find(s=>s.id===attentionId);
 assert.ok(await evaluate(`document.querySelector('[data-translation-scroll]').textContent.includes(${JSON.stringify(attention.translation.faithfulZh)})`),'complete translation');
 await assertPdfFocus(attention);
 await wait("document.querySelector('article.pdf-page-stage canvas')?.width>100",'original page 8 PDF');
 await wait("document.querySelector('[data-companion-window=\"paper-03-figure-2\"] img')?.naturalWidth>500",'Figure 2 relation preserved');
 await click("[...document.querySelectorAll('[data-translation-scroll] button')].find(b=>b.textContent.includes('擷取的原文文字'))");
 await wait(`document.querySelector('[data-translation-scroll]').textContent.includes(${JSON.stringify(attention.sourceText)})`,'complete source text');
 let saved=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)}))`);
 assert.equal(saved.currentSegmentId,attentionId);assert.deepEqual(saved.notes,state.notes);assert.deepEqual(saved.bookmarks,state.bookmarks);
 await evaluate("document.querySelector('[data-translation-scroll]').scrollTop=0");
 const shot=await page.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile('/private/tmp/paper03-attention-fixed-desktop.png',Buffer.from(shot.data,'base64'));
 for(const section of ['3.2 Relevance model','3.3 Confidence model','3.4 Satisfaction model']){
  await click("document.querySelector('.reader-footer button:last-child')");
  await wait(`document.querySelector('[data-translation-scroll]').innerText.includes(${JSON.stringify(section)})`,section+' in sequence');
  await assertPdfFocus(paper.segments.find(s=>s.section===section&&s.kind==='body'&&!s.excluded));
 }
 await click("document.querySelector('button[aria-label=\"開啟段落清單\"]')");
 await wait("document.querySelector('[role=dialog]')",'paragraph list');
 assert.equal(await evaluate("[...document.querySelectorAll('[role=dialog] nav button')].filter(b=>b.textContent.includes('To attract students')).length"),1,'Attention listed once');
 await click("[...document.querySelectorAll('[role=dialog] nav button')].find(b=>b.textContent.includes('To attract students'))");
 await page.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await page.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});
 await wait("!document.querySelector('[role=dialog]')",'list closed');
 await page.send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 await delay(250);
 assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'mobile layout width');
 saved=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)}))`);assert.equal(saved.currentSegmentId,attentionId);assert.deepEqual(saved.notes,state.notes);assert.deepEqual(saved.bookmarks,state.bookmarks);
 await assertPdfFocus(attention);
 await click("[...document.querySelectorAll('[role=tab]')].find(b=>b.textContent.includes('中文翻譯'))");
 await wait("document.querySelector('[data-reader-pane=translation]').getBoundingClientRect().height>100",'mobile translation visible');
 assert.ok(await evaluate(`document.querySelector('[data-translation-scroll]').textContent.includes(${JSON.stringify(attention.translation.faithfulZh)})`));
 const mobileShot=await page.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile('/private/tmp/paper03-attention-fixed-mobile.png',Buffer.from(mobileShot.data,'base64'));
 assert.deepEqual(errors,[]);
 console.log('Paper 3: old draft restored Attention, complete source/translation, PDF, Figure 2, four ARCS sections, list navigation, notes, bookmarks and mobile layout passed.');
}finally{page?.close();try{await browser.send('Target.disposeBrowserContext',{browserContextId});}catch(error){console.error('Browser cleanup: '+error.message);}browser.close();}
