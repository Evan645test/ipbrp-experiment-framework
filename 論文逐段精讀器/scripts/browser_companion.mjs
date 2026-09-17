#!/usr/bin/env node
/* Isolated, non-destructive end-to-end tests against a running reader + Chrome CDP. */
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';

const debugBase=process.env.CHROME_DEBUG_URL ?? 'http://localhost:9222';
const appUrl=process.env.READER_URL ?? 'http://localhost:5173/';
const screenshotDir=process.env.SCREENSHOT_DIR ?? '/private/tmp';
const errors=[];
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function connect(url,onEvent=()=>{}){
  let sequence=0;const pending=new Map();const ws=new WebSocket(url);
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  ws.addEventListener('message',event=>{
    const m=JSON.parse(String(event.data));
    if(m.id&&pending.has(m.id)){const p=pending.get(m.id);clearTimeout(p.timer);pending.delete(m.id);if(m.error)p.reject(new Error(m.error.message));else p.resolve(m.result);}
    else if(m.method)onEvent(m);
  });
  return {send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`CDP timed out: ${method}`));},30000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});},close(){for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('CDP closed'));}pending.clear();ws.close();}};
}

async function main(){
  const version=await(await fetch(`${debugBase}/json/version`)).json();const browser=await connect(version.webSocketDebuggerUrl);
  const {browserContextId}=await browser.send('Target.createBrowserContext',{disposeOnDetach:true});let page;
  try{
    const {targetId}=await browser.send('Target.createTarget',{url:'about:blank',browserContextId});let target;
    for(let i=0;i<50;i++){target=(await(await fetch(`${debugBase}/json/list`)).json()).find(t=>t.id===targetId);if(target?.webSocketDebuggerUrl)break;await delay(100);}
    if(!target?.webSocketDebuggerUrl)throw new Error('Chrome test target not available');
    page=await connect(target.webSocketDebuggerUrl,m=>{
      if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description??m.params.exceptionDetails.text);
      if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')errors.push(m.params.args.map(a=>a.value??a.description).join(' '));
    });
    const send=(method,params={})=>page.send(method,params);
    async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description??r.exceptionDetails.text);return r.result.value;}
    async function wait(expression,label,timeout=20000){const start=Date.now();while(Date.now()-start<timeout){try{if(await evaluate(`Boolean(${expression})`))return;}catch(error){if(!String(error).includes('context')&&!String(error).includes('Cannot read properties'))throw error;}await delay(120);}throw new Error(`Timed out: ${label}\n${await evaluate('document.body?.innerText.slice(0,2200)')}\n${errors.join('\n')}`);}
    async function click(expression){await wait(`!!(${expression})`,'click target ready');await evaluate(`(${expression}).scrollIntoView({block:'nearest'})`);await delay(400);await wait(`(()=>{const e=(${expression});if(!e)return false;const r=e.getBoundingClientRect();const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return r.width>0&&r.height>0&&r.x>=0&&r.y>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1&&(hit===e||e.contains(hit))})()`,'click target visible, settled and unobstructed');const r=await evaluate(`(${expression}).getBoundingClientRect().toJSON()`);const x=r.x+r.width/2,y=r.y+r.height/2;await send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',buttons:1,clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',buttons:0,clickCount:1});await delay(100);}
    async function screenshot(name){await delay(400);const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const path=`${screenshotDir}/${name}`;await writeFile(path,Buffer.from(r.data,'base64'));return path;}
    async function metrics(width,height,mobile=false){await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile});await delay(150);}
    const readerKey='paper-focus-reader:v1:paper-01', companionKey='paper-focus-companion:v1:paper-01';
    async function go(id){await evaluate(`(()=>{const s=JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)}));s.currentSegmentId=${JSON.stringify(id)};localStorage.setItem(${JSON.stringify(readerKey)},JSON.stringify(s));})()`);await send('Page.reload',{ignoreCache:true});await delay(500);await wait(`document.querySelector('.reader-footer')&&JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)})).currentSegmentId===${JSON.stringify(id)}`,'resume requested body');}
    async function assertReaderUnchanged(before){const after=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)}))`);assert.equal(after.currentSegmentId,before.currentSegmentId);assert.deepEqual(after.notes,before.notes);assert.deepEqual(after.bookmarks,before.bookmarks);assert.deepEqual(after.understood,before.understood);}
    async function mouseDrag(selector,dx,dy){const r=await evaluate(`document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect().toJSON()`);const x=r.x+r.width/2,y=r.y+r.height/2;await send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',buttons:1,clickCount:1});for(let i=1;i<=5;i++)await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:x+dx*i/5,y:y+dy*i/5,button:'left',buttons:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:x+dx,y:y+dy,button:'left',buttons:0,clickCount:1});await delay(150);}
    await send('Page.enable');await send('Runtime.enable');await metrics(1600,1000);
    await send('Page.navigate',{url:appUrl});await wait("document.querySelectorAll('article').length===8",'library');
    const old=JSON.parse(await readFile(new URL('../content/paper-01-before-companion.json',import.meta.url),'utf8'));
    await evaluate(`localStorage.setItem('paper-focus-curator:v1:paper-01',${JSON.stringify(JSON.stringify(old))})`);
    await evaluate(`(async()=>{const p=await(await fetch('/data/paper-01.json')).json();localStorage.setItem(${JSON.stringify(readerKey)},JSON.stringify({version:1,paperId:p.id,sourceSha256:p.sourceSha256,currentSegmentId:'paper-01-s-937fa0a15f54',seen:[],understood:['paper-01-s-42e110a0ef05'],bookmarks:['paper-01-s-937fa0a15f54','paper-01-s-42e110a0ef05'],notes:{'paper-01-s-937fa0a15f54':'原隨機效應筆記','paper-01-s-42e110a0ef05':'完整 Table 3 筆記'},dimOpacity:.74,reducedMotion:true,highContrast:false,updatedAt:new Date().toISOString()}));})()`);
    await click("[...document.querySelector('article').querySelectorAll('button')].find(b=>b.innerText.includes('開始閱讀'))");
    await wait("document.querySelector('[data-companion-window=\"paper-01-table-3\"]')",'old random-effect location resumes at Table3 author paragraph');
    await wait("document.querySelector('header').innerText.includes('/ 66')",'66 body steps only');
    const before=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)}))`);assert.equal(before.currentSegmentId,'paper-01-s-77bbe7d39176');
    assert.equal(before.notes['paper-01-s-937fa0a15f54'],'原隨機效應筆記');assert.ok(before.bookmarks.includes('paper-01-s-42e110a0ef05'));
    await wait("document.querySelector('[data-companion-window] img')?.naturalWidth>1900",'complete Table3 native image');
    assert.equal(await evaluate("!!document.querySelector('[data-slot=dialog-overlay]')"),false);
    assert.notEqual(await evaluate("getComputedStyle(document.body).pointerEvents"),'none');
    const wide=await evaluate("(()=>{const p=document.querySelector('[data-reader-pane=translation]').getBoundingClientRect(),e=document.querySelector('[data-companion-window]').getBoundingClientRect(),s=document.querySelector('[data-reader-pane=source]').getBoundingClientRect();return {p:p.toJSON(),e:e.toJSON(),s:s.toJSON()}})()");
    assert.ok(wide.s.right<=wide.p.left+1&&wide.p.right<=wide.e.left+1);
    await screenshot('paper-reader-companion-table3-desktop.png');
    await click("document.querySelector('button[aria-label=\"放大伴讀圖表\"]')");
    await wait("document.querySelector('[aria-label=\"伴讀圖表縮放比例\"]').textContent==='125%'",'image zoom');
    await click("[...document.querySelector('[data-companion-window]').querySelectorAll('button')].find(b=>b.innerText==='浮動')");
    await wait("document.querySelector('[data-companion-dock=floating]')",'non-blocking floating window');
    await mouseDrag('[data-companion-drag-handle]',-80,50);
    const moved=await evaluate("document.querySelector('[data-companion-window]').getBoundingClientRect().toJSON()");assert.ok(moved.x>=0&&moved.right<=1601&&moved.y>=0&&moved.bottom<=1001);
    await mouseDrag('[data-companion-resize-handle]',80,40);
    const resized=await evaluate("document.querySelector('[data-companion-window]').getBoundingClientRect().toJSON()");assert.ok(resized.width>moved.width&&resized.height>moved.height);
    await evaluate("document.querySelector('[data-companion-drag-handle]').focus()");await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
    await assertReaderUnchanged(before);
    // Actual pointer release onto the visible source drop zone must dock.
    const handle=await evaluate("document.querySelector('[data-companion-drag-handle]').getBoundingClientRect().toJSON()");
    const source=await evaluate("document.querySelector('[data-reader-pane=source]').getBoundingClientRect().toJSON()");
    const sx=handle.x+handle.width/2,sy=handle.y+handle.height/2,tx=source.x+source.width/2,ty=source.y+30;
    await send('Input.dispatchMouseEvent',{type:'mousePressed',x:sx,y:sy,button:'left',buttons:1,clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:tx,y:ty,button:'left',buttons:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:tx,y:ty,button:'left',buttons:0,clickCount:1});
    await wait("document.querySelector('[data-companion-dock=source]')",'drag-to-dock source zone');
    await click("[...document.querySelector('[data-companion-window]').querySelectorAll('button')].find(b=>b.innerText==='翻譯旁')");
    await click("document.querySelector('button[aria-label=\"收起本段伴讀圖表\"]')");await wait("!document.querySelector('[data-companion-window]')",'close affects current paragraph');
    await assertReaderUnchanged(before);
    await click("[...document.querySelector('.reader-footer').querySelectorAll('button')].find(b=>b.innerText.includes('下一段'))");
    await wait("document.querySelector('[data-companion-window=\"paper-01-table-4\"]')",'next body automatically opens table4, no caption step');
    await wait("document.querySelectorAll('[data-companion-tab]').length===2",'table4 and fig12 tabs');
    await click("[...document.querySelector('.reader-footer').querySelectorAll('button')].find(b=>b.innerText.includes('上一段'))");
    await wait("document.querySelector('[data-companion-window=\"paper-01-table-3\"]')",'manual collapse expires after leaving paragraph');
    await click("[...document.querySelector('.reader-footer').querySelectorAll('button')].find(b=>b.innerText.includes('下一段'))");
    await wait("document.querySelectorAll('[data-companion-tab]').length===2",'return to table4 and fig12 tabs');
    await click("document.querySelector('[data-companion-tab=\"paper-01-figure-12\"]')");await wait("document.querySelector('[data-companion-study=\"paper-01-figure-12\"]')",'interpretation follows selected chart');
    await screenshot('paper-reader-companion-figure12-desktop.png');
    await go('paper-01-s-190b05a24c0c');await wait("document.querySelector('[data-companion-window=\"paper-01-figure-2\"]')",'semantic link without figure number auto opens');
    await wait("document.querySelector('[data-companion-study]').innerText.includes('未寫圖號')",'semantic relationship shown');
    await metrics(1200,900);const narrow=await evaluate("(()=>{const e=document.querySelector('[data-companion-window]').getBoundingClientRect(),p=document.querySelector('[data-reader-pane=translation]').getBoundingClientRect();return {e:e.toJSON(),p:p.toJSON()}})()");assert.ok(narrow.e.bottom<=narrow.p.top+1);
    await metrics(390,844,true);await wait("document.querySelector('[data-companion-window]').getBoundingClientRect().width<=390",'mobile exhibit fits');
    await click("[...document.querySelectorAll('[role=tab]')].find(b=>b.innerText==='中文翻譯')");
    await screenshot('paper-reader-companion-mobile.png');
    const mobile=await evaluate("(()=>{const e=document.querySelector('[data-companion-window]').getBoundingClientRect(),p=document.querySelector('[data-reader-pane=translation]').getBoundingClientRect();return {e:e.toJSON(),p:p.toJSON(),width:innerWidth,height:innerHeight,grid:getComputedStyle(document.querySelector('.companion-workspace')).gridTemplateAreas,display:getComputedStyle(document.querySelector('[data-reader-pane=translation]')).display,overflow:document.documentElement.scrollWidth>innerWidth}})()");assert.ok(mobile.e.bottom<=mobile.p.top+1,JSON.stringify(mobile));assert.ok(mobile.p.height>150);assert.equal(mobile.overflow,false);
    // Touch dragging floats the same non-modal window; docking remains available by button.
    const touch=await evaluate("document.querySelector('[data-companion-drag-handle]').getBoundingClientRect().toJSON()");const touchX=touch.x+touch.width/2,touchY=touch.y+touch.height/2;
    await send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:touchX,y:touchY}]});await send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:touchX,y:touchY+70}]});await send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    await wait("document.querySelector('[data-companion-dock=floating]')",'touch drag');
    await click("[...document.querySelector('[data-companion-window]').querySelectorAll('button')].find(b=>b.innerText==='翻譯旁')");
    await metrics(1600,1000);await go('paper-01-s-77bbe7d39176');
    await wait("document.querySelector('[aria-label=\"伴讀圖表縮放比例\"]').textContent==='125%'",'per-exhibit zoom persists after segment changes/reload');
    // The guide moves with the figure and paragraph reading exposes only the current passage.
    assert.equal(await evaluate("document.querySelectorAll('[data-companion-source]').length"),1);
    assert.equal(await evaluate("document.querySelector('[data-companion-source]').dataset.companionSource"),'paper-01-s-77bbe7d39176');
    assert.equal(await evaluate("!!document.querySelector('[data-translation-scroll] [data-companion-study]')"),false);
    assert.equal(await evaluate("!!document.querySelector('[data-companion-window] [data-exhibit-guide]')"),true);
    await assertReaderUnchanged(before);
    const candidate=await evaluate("(async()=>{const p=await(await fetch('/data/paper-01.json')).json();return p.exhibitCompanion.links.find(l=>l.confidence==='candidate')})()");
    await go(candidate.segmentId);await wait("document.querySelector('[data-companion-candidates]')",'weak candidate is offered');
    await evaluate("document.querySelector('[data-companion-candidates]').open=true");
    await click("[...document.querySelector('[data-companion-candidates]').querySelectorAll('button')].find(b=>b.innerText==='確認加入伴讀')");
    await wait(`JSON.parse(localStorage.getItem(${JSON.stringify(companionKey)})).corrections[${JSON.stringify(candidate.segmentId)}]?.[${JSON.stringify(candidate.exhibitId)}]==='include'`,'candidate approval persists');
    // Export is the complete validated JSON state; verify import at real file input.
    await click("document.querySelector('button[aria-label=\"閱讀設定\"]')");await wait("document.querySelector('[role=dialog]')",'settings');
    const backup=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(companionKey)}))`);
    await screenshot('paper-reader-companion-settings.png');
    await evaluate("(()=>{window.__testCreateUrl=URL.createObjectURL;window.__testAnchorClick=HTMLAnchorElement.prototype.click;URL.createObjectURL=blob=>{window.__testExportBlob=blob;return window.__testCreateUrl(blob)};HTMLAnchorElement.prototype.click=function(){if(!this.download)return window.__testAnchorClick.call(this)};})()");
    await click("[...document.querySelector('[role=dialog]').querySelectorAll('button')].find(b=>b.innerText==='匯出伴讀修正')");
    await wait("window.__testExportBlob instanceof Blob",'export button creates companion backup blob');
    const exported=await evaluate("(async()=>JSON.parse(await window.__testExportBlob.text()))()");assert.deepEqual(exported,backup);
    await evaluate("URL.createObjectURL=window.__testCreateUrl;HTMLAnchorElement.prototype.click=window.__testAnchorClick");
    const imported=structuredClone(backup);imported.layout.dock='source';
    await evaluate(`(()=>{const input=document.querySelector('input[aria-label=\"匯入伴讀修正檔案\"]');const transfer=new DataTransfer();transfer.items.add(new File([${JSON.stringify(JSON.stringify(imported))}],'companion.json',{type:'application/json'}));input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await wait(`JSON.parse(localStorage.getItem(${JSON.stringify(companionKey)})).layout.dock==='source'`,'valid backup import');
    const invalid={...imported,sourceSha256:'wrong'};await evaluate(`(()=>{const input=document.querySelector('input[aria-label=\"匯入伴讀修正檔案\"]');const transfer=new DataTransfer();transfer.items.add(new File([${JSON.stringify(JSON.stringify(invalid))}],'wrong.json',{type:'application/json'}));input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await wait("document.querySelector('output[aria-live=polite]').innerText.includes('PDF 版本')",'wrong PDF backup rejected');
    assert.deepEqual(await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(companionKey)}))`),imported);
    await click("[...document.querySelector('[role=dialog]').querySelectorAll('button')].find(b=>b.textContent.trim()==='Close')");
    await click("document.querySelector('button[aria-label=\"查看本篇全部圖表\"]')");
    await wait("document.querySelectorAll('[data-companion-catalog]').length===25",'all25 complete exhibits remain accessible');
    await evaluate("document.querySelector('[data-companion-catalog=\"paper-01-table-3\"] details').open=true");
    await wait("document.querySelector('[role=dialog]').innerText.includes('原隨機效應筆記')",'archived table fragment notes visible');
    await screenshot('paper-reader-companion-catalog.png');
    await click("[...document.querySelector('[role=dialog]').querySelectorAll('button')].find(b=>b.textContent.trim()==='Close')");
    // Ensure unrelated body automatically hides previous chart.
    const unrelated=await evaluate("(async()=>{const p=await(await fetch('/data/paper-01.json')).json();return p.segments.find(s=>!s.excluded&&s.kind==='body'&&!p.exhibitCompanion.links.some(l=>l.segmentId===s.id&&l.confidence==='high')).id})()");
    await go(unrelated);assert.equal(await evaluate("!!document.querySelector('[data-companion-window]')"),false);
    await go('paper-01-s-190b05a24c0c');
    assert.equal(await evaluate("document.querySelector('[data-companion-source]').dataset.companionSource"),'paper-01-s-190b05a24c0c');
    await evaluate("(()=>{document.querySelector('[data-translation-scroll]').scrollTop=170;document.querySelector('[data-pdf-scroller]').scrollTop=90;document.querySelector('[data-companion-content-scroll]').scrollTop=180;document.querySelector('[data-companion-study] details').open=true})()");
    const originState=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)}))`);
    const originalCompanion=await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(companionKey)}))`);
    const snapshot=()=>evaluate("(()=>{const e=document.querySelector('[data-companion-window]');return {chart:e.dataset.companionWindow,translation:document.querySelector('[data-translation-scroll]').scrollTop,pdf:document.querySelector('[data-pdf-scroller]').scrollTop,content:document.querySelector('[data-companion-content-scroll]').scrollTop,guide:e.querySelector('[data-companion-study] details').open}})()");
    const originView=await snapshot();
    async function overview(id){await click("document.querySelector('button[aria-label=\"查看本篇全部圖表\"]')");await click(`[...document.querySelector('[data-companion-catalog="${id}"]').querySelectorAll('button')].find(b=>b.innerText==='查看完整圖表')`);await wait(`document.querySelector('[data-exhibit-overview="${id}"]')&&!document.querySelector('[role=dialog]')`,'independent non-modal overview');}
    async function closeOverview(){await click("document.querySelector('button[aria-label=\"關閉圖表總覽，返回原閱讀畫面\"]')");await wait("!document.querySelector('[data-exhibit-overview]')",'overview closes');}
    await overview('paper-01-figure-2');
    assert.equal(await evaluate("getComputedStyle(document.querySelector('[data-companion-window]')).visibility"),'hidden');
    assert.equal(await evaluate("!!document.querySelector('[data-slot=dialog-overlay]')"),false);
    assert.notEqual(await evaluate("getComputedStyle(document.body).pointerEvents"),'none');
    const geometry=await evaluate("(()=>{const a=document.querySelector('[data-overview-picture]').getBoundingClientRect(),b=document.querySelector('[data-overview-explanations]').getBoundingClientRect();return {a:a.toJSON(),b:b.toJSON()}})()");
    assert.ok(geometry.a.right<=geometry.b.left+1);
    assert.equal(await evaluate("document.querySelectorAll('[data-overview-source]').length"),4);
    assert.equal(await evaluate("[...document.querySelectorAll('[data-overview-source]')].every(e=>!e.open)"),true);
    assert.ok(await evaluate("document.querySelector('[data-overview-explanations]').innerText.includes('語意關聯')"));
    assert.ok(await evaluate("document.querySelector('[data-overview-explanations]').innerText.includes('明確引用')"));
    const expectedOrder=await evaluate("(async()=>{const p=await(await fetch('/data/paper-01.json')).json();const ids=[...document.querySelectorAll('[data-overview-source]')].map(e=>e.dataset.overviewSource);return ids.map(id=>p.segments.find(s=>s.id===id).order)})()");assert.deepEqual(expectedOrder,expectedOrder.toSorted((a,b)=>a-b));
    await evaluate("document.querySelector('[data-overview-source]').open=true;document.querySelector('[data-overview-explanations] [data-exhibit-guide] details').open=true");
    await screenshot('paper-reader-overview-desktop.png');
    await click("document.querySelector('button[aria-label=\"放大總覽圖表\"]')");
    await wait("document.querySelector('[aria-label=\"總覽圖表縮放比例\"]').textContent==='125%'",'overview has its own image zoom');
    const beforeMove=await evaluate("document.querySelector('[data-exhibit-overview]').getBoundingClientRect().toJSON()");
    await mouseDrag('[data-overview-drag-handle]',40,20);
    const afterMove=await evaluate("document.querySelector('[data-exhibit-overview]').getBoundingClientRect().toJSON()");assert.ok(afterMove.x>beforeMove.x&&afterMove.y>beforeMove.y);
    await mouseDrag('[data-overview-resize-handle]',70,35);
    assert.ok(await evaluate(`document.querySelector('[data-exhibit-overview]').getBoundingClientRect().width>${afterMove.width}`));
    await evaluate("document.querySelector('[data-overview-drag-handle]').focus()");await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
    await assertReaderUnchanged(originState);assert.deepEqual(await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)})).seen`),originState.seen);
    await closeOverview();assert.deepEqual(await snapshot(),originView);
    assert.deepEqual(await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(companionKey)}))`),originalCompanion);
    await overview('paper-01-figure-2');await wait("document.querySelector('[aria-label=\"總覽圖表縮放比例\"]').textContent==='125%'",'overview zoom survives closing without changing companion zoom');
    await metrics(390,844,true);
    const mobileOverview=await evaluate("(()=>{const e=document.querySelector('[data-exhibit-overview]').getBoundingClientRect(),a=document.querySelector('[data-overview-picture]').getBoundingClientRect(),b=document.querySelector('[data-overview-explanations]').getBoundingClientRect();return {e:e.toJSON(),a:a.toJSON(),b:b.toJSON(),overflow:document.documentElement.scrollWidth>innerWidth}})()");
    assert.ok(mobileOverview.a.bottom<=mobileOverview.b.top+1);assert.ok(mobileOverview.b.height>120);assert.ok(mobileOverview.e.x>=0&&mobileOverview.e.right<=391);assert.equal(mobileOverview.overflow,false);
    await screenshot('paper-reader-overview-mobile.png');
    const split=await evaluate("document.querySelector('[data-overview-split-handle]').getBoundingClientRect().toJSON()");const splitX=split.x+split.width/2,splitY=split.y+split.height/2;
    await send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:splitX,y:splitY}]});await send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:splitX,y:splitY-45}]});await send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    assert.ok(await evaluate(`document.querySelector('[data-overview-picture]').getBoundingClientRect().height<${mobileOverview.a.height}`));
    const touchHandle=await evaluate("document.querySelector('[data-overview-drag-handle]').getBoundingClientRect().toJSON()");
    const overviewTouchX=touchHandle.x+touchHandle.width/2,overviewTouchY=touchHandle.y+touchHandle.height/2;
    await send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:overviewTouchX,y:overviewTouchY}]});await send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:overviewTouchX,y:overviewTouchY-30}]});await send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
    assert.ok(await evaluate(`document.querySelector('[data-exhibit-overview]').getBoundingClientRect().y<${mobileOverview.e.y}`));
    await closeOverview();await metrics(1600,1000);await assertReaderUnchanged(originState);
    await overview(candidate.exhibitId);assert.ok(await evaluate(`document.querySelector('[data-overview-source="${candidate.segmentId}"]')?.querySelector('summary').textContent.includes('使用者加入')`));await closeOverview();
    // Supplement browsing never advances the body reader or marks it read.
    await click("document.querySelector('button[aria-label=\"查看完整附錄\"]')");
    await wait("document.querySelector('[data-paper-supplements]')",'appendix sheet');
    assert.equal(await evaluate("document.querySelectorAll('[data-supplement-statement]').length"),0);
    await assertReaderUnchanged(originState);assert.deepEqual(await evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(readerKey)})).seen`),originState.seen);
    await wait("document.querySelector('[data-complete-appendix=\"paper-01-appendix-i\"] img')?.naturalWidth>1900",'complete native Appendix I');
    await click("document.querySelector('button[aria-label=\"放大附錄圖表\"]')");
    await wait("document.querySelector('[aria-label=\"附錄圖表縮放比例\"]').textContent==='125%'",'appendix image zoom');
    await click("document.querySelector('[data-appendix-tab=\"paper-01-appendix-ii\"]')");
    await wait("document.querySelector('[data-complete-appendix=\"paper-01-appendix-ii\"] img')?.naturalWidth>1900",'complete native Appendix II');
    assert.ok(await evaluate("['Go/No-Go','Mr. Ant','Card Sorting'].every(t=>document.querySelector('[data-appendix-translation]').textContent.includes(t))"));
    await screenshot('paper-reader-appendix-desktop.png');
    await metrics(390,844,true);
    assert.equal(await evaluate("document.documentElement.scrollWidth>innerWidth"),false);
    const appendixGeometry=await evaluate("(()=>{const a=document.querySelector('[data-complete-appendix]'),r=a.children[0].getBoundingClientRect(),t=a.children[1].getBoundingClientRect();return {r:r.toJSON(),t:t.toJSON()}})()");
    assert.ok(appendixGeometry.r.bottom<=appendixGeometry.t.top);
    await screenshot('paper-reader-appendix-mobile.png');
    await click("[...document.querySelectorAll('[data-slot=sheet-content] button')].find(b=>b.textContent==='Close')");
    await wait("!document.querySelector('[data-paper-supplements]')",'supplements closed');
    await metrics(1600,1000);await assertReaderUnchanged(originState);
    await go('paper-01-s-806f9b6ab1aa');
    await wait("document.querySelectorAll('article.pdf-page-stage').length===2",'future recommendations restored across both source pages');
    assert.ok(await evaluate("[1,2,3,4,5].every(n=>document.querySelector('[data-translation-scroll]').textContent.includes('（'+n+'）'))"));
    await screenshot('paper-reader-future-recommendations.png');
    await click("document.querySelector('button[aria-label=\"查看完整附錄\"]')");
    await wait("document.querySelector('[data-paper-supplements]')",'appendices available after body navigation');
    await click("[...document.querySelectorAll('[data-slot=sheet-content] button')].find(b=>b.textContent==='Close')");
    // A preserved local explanation edit must not silently appear as checked.
    const guarded=await evaluate("(async()=>{const p=await(await fetch('/data/paper-01.json')).json();const s=p.segments.find(s=>s.sourceText.startsWith('Table 2 shows'));s.translation.plainZh='保留我的人工修改，不冒充核對稿';localStorage.setItem('paper-focus-curator:v1:paper-01',JSON.stringify(p));return s.id})()");
    await go(guarded);
    await click("[...document.querySelectorAll('[data-translation-scroll] button')].find(b=>b.textContent.includes('白話解釋'))");
    await wait("document.querySelector('[data-explanation-fidelity-guard]')",'changed explanation is visibly guarded');
    assert.equal(await evaluate(`JSON.parse(localStorage.getItem('paper-focus-curator:v1:paper-01')).segments.find(s=>s.id===${JSON.stringify(guarded)}).translation.plainZh`),'保留我的人工修改，不冒充核對稿');
    assert.equal(errors.length,0,errors.join('\n'));
    console.log(JSON.stringify({bodySteps:66,exhibits:25,oldCuratorAndTableProgress:'passed',nonModal:'passed',semanticAndCandidateLinks:'passed',dragDockResizeKeyboardTouch:'passed',imageZoomPersistence:'passed',desktopTabletMobile:'passed',followParagraphAndClose:'passed',archiveNotesAndBookmarks:'passed',backupImportAndWrongPdfGuard:'passed',guideMovesWithChartAndOnlyCurrentPassage:'passed',overviewLeftChartRightOrderedPassages:'passed',overviewIndependentDragResizeZoomAndMobileSplit:'passed',overviewRestoresOriginalScrollGuideChartAndProgress:'passed',consoleErrors:errors.length,screenshots:screenshotDir},null,2));
  }finally{page?.close();await browser.send('Target.disposeBrowserContext',{browserContextId});browser.close();}
}
main().catch(error=>{console.error(error.stack??error);process.exitCode=1;});
