#!/usr/bin/env node
/* End-to-end smoke test for a running local reader via Chrome DevTools Protocol. */

import { readFile, writeFile } from "node:fs/promises";

const debugBase = process.env.CHROME_DEBUG_URL ?? "http://127.0.0.1:9222";
const appUrl = process.env.READER_URL ?? "http://localhost:5173/";
const screenshotDir = process.env.SCREENSHOT_DIR ?? "/private/tmp";
const consoleErrors = [];
let pageLoadCount = 0;

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function connect(webSocketUrl, onEvent = () => {}) {
  let sequence = 0;
  const pending = new Map();
  const socket = new WebSocket(webSocketUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data));
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
      return;
    }
    if (message.method) onEvent(message);
  });

  return {
    send(method, params = {}) {
      sequence += 1;
      return new Promise((resolve, reject) => {
        pending.set(sequence, { resolve, reject });
        socket.send(JSON.stringify({ id: sequence, method, params }));
      });
    },
    close() {
      socket.close();
    },
  };
}

async function main() {
  const versionResponse = await fetch(`${debugBase}/json/version`);
  if (!versionResponse.ok) throw new Error(`Chrome version endpoint returned ${versionResponse.status}`);
  const version = await versionResponse.json();
  const browser = await connect(version.webSocketDebuggerUrl);
  const { browserContextId } = await browser.send("Target.createBrowserContext", { disposeOnDetach: true });
  let page;
  try {
    const { targetId } = await browser.send("Target.createTarget", { url: "about:blank", browserContextId });
    let target;
    for (let attempt = 0; attempt < 50; attempt += 1) {
      const targets = await (await fetch(`${debugBase}/json/list`)).json();
      target = targets.find((entry) => entry.id === targetId);
      if (target?.webSocketDebuggerUrl) break;
      await delay(100);
    }
    if (!target?.webSocketDebuggerUrl) throw new Error("Chrome test target did not become available");
    page = await connect(target.webSocketDebuggerUrl, (message) => {
      if (message.method === "Page.loadEventFired") pageLoadCount += 1;
      if (message.method === "Runtime.exceptionThrown") {
        consoleErrors.push(message.params.exceptionDetails.text);
      }
      if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
        consoleErrors.push(message.params.args.map((entry) => entry.value ?? entry.description ?? "error").join(" "));
      }
    });

  async function send(method, params = {}) {
    const previousLoad = pageLoadCount;
    const result = await page.send(method, params);
    if (method === "Page.reload" || method === "Page.navigate") {
      const started = Date.now();
      while (pageLoadCount <= previousLoad && Date.now() - started < 20000) await delay(100);
      if (pageLoadCount <= previousLoad) throw new Error(`${method} did not finish loading a new document`);
    }
    return result;
  }

  async function evaluate(expression) {
    const result = await send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text);
    return result.result.value;
  }

  async function waitFor(expression, label, timeout = 15000) {
    const started = Date.now();
    while (Date.now() - started < timeout) {
      if (await evaluate(expression)) return;
      await delay(150);
    }
    const body = await evaluate("document.body.innerText.slice(0, 1800)");
    const geometry = await evaluate("(()=>{const e=document.querySelector('[data-exhibit-preview]');const r=e?.getBoundingClientRect();return {viewport:[innerWidth,innerHeight],dialog:r?.toJSON(),style:e?.getAttribute('style')}})()");
    throw new Error(`Timed out waiting for ${label}\nConsole: ${consoleErrors.join(" | ") || "none"}\nGeometry: ${JSON.stringify(geometry)}\nPage: ${body}`);
  }

  async function screenshot(name) {
    await delay(650);
    const result = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
    const path = `${screenshotDir}/${name}`;
    await writeFile(path, Buffer.from(result.data, "base64"));
    return path;
  }

  async function clickAt(expression) {
    const point = await evaluate(`(() => {
      const element = ${expression};
      if (!element) throw new Error('Target element not found');
      const rect = element.getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    })()`);
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x: point.x, y: point.y, button: "left", clickCount: 1 });
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: point.x, y: point.y, button: "left", clickCount: 1 });
  }

  async function verifyReferenceReturn(label) {
    const origin = await evaluate(`(() => {
      const key='paper-focus-reader:v1:paper-01';
      const state=JSON.parse(localStorage.getItem(key));
      const dialog=document.querySelector('[role=dialog]');
      const scroller=dialog.querySelector('.scrollbar-thin');
      const buttons=[...dialog.querySelectorAll('[data-reference-segment-id]')];
      const button=buttons.find(entry=>entry.dataset.referenceSegmentId!==state.currentSegmentId)??buttons[0];
      if(!button)throw new Error('找不到引用段落跳轉按鈕');
      scroller.scrollTop=button.offsetTop;
      const result={key,segmentId:state.currentSegmentId,targetId:button.dataset.referenceSegmentId,title:dialog.querySelector('h2').textContent,scrollTop:scroller.scrollTop,notes:state.notes,understood:state.understood};
      button.click();
      return result;
    })()`);
    await waitFor("!document.querySelector('[role=dialog]')",`${label} jump closes reference sheet`);
    await waitFor(`JSON.parse(localStorage.getItem(${JSON.stringify(origin.key)})).currentSegmentId===${JSON.stringify(origin.targetId)}`,`${label} reaches cited passage`);
    await waitFor("!!document.querySelector('button[aria-label=\"返回上一個位置\"]')",`${label} return button available`);
    await waitFor("(()=>{const r=document.querySelector('button[aria-label=\"返回上一個位置\"]').getBoundingClientRect();return r.width>0&&r.left>=0&&r.right<=innerWidth+1})()",`${label} return button fits viewport`);
    await waitFor("[...document.querySelectorAll('.reader-footer button')].every(entry=>{const r=entry.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1})",`${label} all footer buttons fit viewport`);
    await screenshot(`paper-reader-reference-return-${label}.png`);
    await evaluate("document.querySelector('button[aria-label=\"返回上一個位置\"]').click()");
    await waitFor(`JSON.parse(localStorage.getItem(${JSON.stringify(origin.key)})).currentSegmentId===${JSON.stringify(origin.segmentId)}`,`${label} restores origin passage`);
    await waitFor(`document.querySelector('[role=dialog] h2')?.textContent===${JSON.stringify(origin.title)}`,`${label} restores selected reference`);
    await waitFor(`Math.abs(document.querySelector('[role=dialog] .scrollbar-thin').scrollTop-${origin.scrollTop})<2`,`${label} restores reference scroll position`);
    await waitFor("!document.querySelector('button[aria-label=\"返回上一個位置\"]')",`${label} consumed history hides return button`);
    await waitFor(`(()=>{const state=JSON.parse(localStorage.getItem(${JSON.stringify(origin.key)}));return JSON.stringify(state.notes)===${JSON.stringify(JSON.stringify(origin.notes))}&&JSON.stringify(state.understood)===${JSON.stringify(JSON.stringify(origin.understood))}})()`,`${label} preserves notes and understood marks`);
  }

  await send("Page.enable");
  await send("Runtime.enable");
  // This suite exercises the unchanged, non-companion reader branch and all
  // historical migration paths. The companion suite separately tests the live
  // first-paper feature. Override only this isolated test context's response.
  if (process.env.READER_LEGACY_EXHIBITS === "1") {
    const legacy=JSON.parse(await readFile(new URL('../content/paper-01-before-reading-quality.json',import.meta.url),'utf8')).paper;
    delete legacy.exhibitCompanion;
    await send("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
      const original=window.fetch;
      window.fetch=async (...args)=>{
        const response=await original(...args);
        if(new URL(response.url).pathname!=='/data/paper-01.json')return response;
        const value=${JSON.stringify(legacy)};
        return new Response(JSON.stringify(value),{status:response.status,headers:response.headers});
      };
    })();` });
  }
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await send("Page.navigate", { url: appUrl });
  await waitFor("document.querySelectorAll('article').length === 8", "eight-paper library");
  const orderFixture = await evaluate(`(async () => {
    const paper=await (await fetch('/data/paper-01.json')).json();
    if(!paper.readingOrderRepair)throw new Error('Paper-01 order repair is missing');
    const byId=new Map(paper.segments.map(entry=>[entry.id,entry]));
    const old=structuredClone(paper);delete old.readingOrderRepair;
    old.segments=paper.readingOrderRepair.previousSegmentIds.map((id,index)=>({...byId.get(id),order:index+1}));
    old.segments.find(entry=>entry.id==='paper-01-s-fb4b491173bb').excluded=undefined;
    const preservedId=old.segments.find(entry=>entry.sourceText.startsWith('The teaching approach')).id;
    old.segments.find(entry=>entry.id===preservedId).translation.plainZh='preserved local explanation';
    const key='paper-focus-curator:v1:paper-01';localStorage.setItem(key,JSON.stringify(old));
    return {key,preservedId,firstRestoredId:'paper-01-s-bd0df1233583',count:paper.segments.filter(entry=>!entry.excluded).length};
  })()`);
  await evaluate("[...document.querySelector('article').querySelectorAll('button')].find(button=>button.innerText.includes('開始閱讀')).click()");
  await waitFor(`document.querySelector('header')?.innerText.includes('/ '+${orderFixture.count})`,"old paper-01 curator draft inherits corrected sequence and recovered paragraphs");
  await clickAt("Array.from(document.querySelectorAll('button')).find(entry=>entry.innerText.includes('下一段'))");
  await waitFor(`JSON.parse(localStorage.getItem('paper-focus-reader:v1:paper-01')).currentSegmentId===${JSON.stringify(orderFixture.firstRestoredId)}`,"abstract advances to original introduction first paragraph");
  await waitFor(`document.body.innerText.includes('運算思維（CT）是一組讓個人運用電腦科學原理')`,"restored paragraph Chinese translation displayed");
  await screenshot("paper-reader-paper01-order-restored.png");
  for (const expectedId of ['paper-01-s-dd5aa63837c8','paper-01-s-6e363a12658d',orderFixture.preservedId]) {
    await clickAt("Array.from(document.querySelectorAll('button')).find(entry=>entry.innerText.includes('下一段'))");
    await waitFor(`JSON.parse(localStorage.getItem('paper-focus-reader:v1:paper-01')).currentSegmentId===${JSON.stringify(expectedId)}`,"restored introduction advances in native paragraph order");
  }
  await evaluate("Array.from(document.querySelectorAll('button')).find(entry=>entry.innerText==='白話解釋').click()");
  await waitFor("document.body.innerText.includes('preserved local explanation')", "order repair preserves local translation edits");
  await evaluate(`localStorage.removeItem(${JSON.stringify(orderFixture.key)});localStorage.removeItem('paper-focus-reader:v1:paper-01');`);
  await evaluate("document.querySelector('button[aria-label=\"回到論文書庫\"]').click()");
  await waitFor("document.querySelectorAll('article').length === 8", "return from paper-01 order checks");
  const spotFixture = await evaluate(`(async()=>{
    const paper=await(await fetch('/data/paper-01.json')).json();
    const key='paper-focus-reader:v1:paper-01';
    const state={version:1,paperId:paper.id,sourceSha256:paper.sourceSha256,currentSegmentId:'paper-01-s-11c642e44a44',seen:[],understood:[],bookmarks:['paper-01-s-11c642e44a44'],notes:{'paper-01-s-11c642e44a44':'preserved cross-page note'},dimOpacity:.74,reducedMotion:true,highContrast:false,updatedAt:new Date().toISOString()};
    localStorage.setItem(key,JSON.stringify(state));return {key};
  })()`);
  await evaluate("[...document.querySelector('article').querySelectorAll('button')].find(button=>button.innerText.includes('開始閱讀')).click()");
  await waitFor("JSON.parse(localStorage.getItem('paper-focus-reader:v1:paper-01')).currentSegmentId==='paper-01-s-c92507a4832b'",'old continuation position resumes at full merged paragraph');
  await waitFor("document.body.innerText.includes('Kappa 值為 0.83，顯示具有良好的信度')",'full cross-page paragraph translation includes ending');
  await waitFor("document.querySelectorAll('.pdf-page-stage canvas').length===2",'merged paragraph renders both source pages without table text mixed in');
  const interruptionCases = await evaluate("(async()=>{const paper=await(await fetch('/data/paper-01.json')).json();return paper.readingUnitRepairs.filter(r=>r.revision==='paper-01-exhibit-interruptions-v1').map(r=>({target:r.targetId,tail:r.absorbedIds[0],translation:paper.segments.find(s=>s.id===r.targetId).translation.faithfulZh.slice(0,35)}))})()");
  if (interruptionCases.length !== 6) throw new Error('Expected all six additional paragraph interruptions');
  for (const entry of interruptionCases) {
    await evaluate(`(()=>{const key=${JSON.stringify(spotFixture.key)};const state=JSON.parse(localStorage.getItem(key));state.currentSegmentId=${JSON.stringify(entry.tail)};localStorage.setItem(key,JSON.stringify(state))})()`);
    await send('Page.reload',{ignoreCache:true});
    await waitFor(`JSON.parse(localStorage.getItem(${JSON.stringify(spotFixture.key)})).currentSegmentId===${JSON.stringify(entry.target)}`,'interrupted continuation resumes at complete source paragraph');
    await waitFor(`document.body.innerText.includes(${JSON.stringify(entry.translation)})`,'merged paragraph has complete regenerated translation');
    await waitFor("document.querySelectorAll('.pdf-page-stage canvas').length===2",'merged paragraph retains both original PDF page fragments');
  }
  await screenshot('paper-reader-interrupted-discussion-merged.png');
  const tableCases = await evaluate("(async()=>{const paper=await(await fetch('/data/paper-01.json')).json();return paper.exhibits.filter(e=>e.kind==='table').map(e=>({id:e.id,target:e.captionSegmentId,number:e.number,image:e.imageUrl,bbox:e.bbox,translation:paper.segments.find(s=>s.id===e.captionSegmentId).translation.faithfulZh.slice(0,25)}))})()");
  if (tableCases.length !== 10) throw new Error('Expected ten complete independent tables');
  for (const entry of tableCases) {
    await evaluate(`(()=>{const key=${JSON.stringify(spotFixture.key)};const state=JSON.parse(localStorage.getItem(key));state.currentSegmentId=${JSON.stringify(entry.target)};localStorage.setItem(key,JSON.stringify(state))})()`);
    await send('Page.reload',{ignoreCache:true});
    await waitFor(`document.body?.innerText.includes(${JSON.stringify(entry.translation)})`,'complete table translation is available in one reading step');
    await waitFor("document.querySelector('.pdf-page-stage canvas')?.width>0",'complete table original PDF rendered');
    if (entry.number === '3') {
      await waitFor("document.querySelector('footer')?.innerText.includes('5.1. Analysis of computational thinking (CT)')",'Table 3 section correctly belongs to computational thinking');
      await waitFor("['固定效應','隨機效應','模型配適','模型公式'].every(text=>document.body?.innerText.includes(text))",'all Table 3 sections are read together');
      await screenshot('paper-reader-table3-complete-step.png');
      const tableState = await evaluate("localStorage.getItem('paper-focus-reader:v1:paper-01')");
      await evaluate("document.querySelector('[data-exhibit-mention=\"paper-01-table-3\"]').click()");
      await waitFor("document.querySelector('[data-exhibit-preview=\"paper-01-table-3\"] img')?.naturalWidth>0",'Table 3 popup contains complete original table');
      await waitFor("document.querySelector('[data-exhibit-preview] img')?.src.includes('tab3_p12_complete.png')",'Table 3 uses source-verified full caption, cells and note crop');
      await screenshot('paper-reader-table3-complete-popup.png');
      await evaluate("[...document.querySelectorAll('[data-exhibit-preview] button')].find(button=>button.innerText.includes('關閉，繼續閱讀')).click()");
      await waitFor(`localStorage.getItem('paper-focus-reader:v1:paper-01')===${JSON.stringify(tableState)}`,'complete table popup preserves reading state');
      await clickAt("Array.from(document.querySelectorAll('button')).find(button=>button.innerText.includes('下一段'))");
      await waitFor("JSON.parse(localStorage.getItem('paper-focus-reader:v1:paper-01')).currentSegmentId==='paper-01-s-e30e9b5f5b12'",'next step skips archived Table 3 pieces and opens complete Table 4');
    }
  }
  await evaluate(`(()=>{const key=${JSON.stringify(spotFixture.key)};const state=JSON.parse(localStorage.getItem(key));state.currentSegmentId='paper-01-s-3b225b28632e';localStorage.setItem(key,JSON.stringify(state))})()`);
  await send('Page.reload',{ignoreCache:true});
  await waitFor("!!document.querySelector('[data-pdf-exhibit-mention=\"paper-01-table-2\"]')",'original Table 2 label is clickable');
  await delay(500);
  const unchangedBeforePreview = await evaluate("localStorage.getItem('paper-focus-reader:v1:paper-01')");
  await clickAt("document.querySelector('[data-pdf-exhibit-mention=\"paper-01-table-2\"]')");
  await waitFor("document.querySelector('[data-exhibit-preview=\"paper-01-table-2\"] img')?.naturalWidth>0",'native PDF label opens full table directly');
  await waitFor("document.querySelector('[data-exhibit-preview] img').src.includes('tab2_p11_complete.png')",'preview uses complete table caption and rows');
  await screenshot('paper-reader-table2-inline-preview.png');
  const beforeDrag = await evaluate("(()=>{const r=document.querySelector('[data-exhibit-preview]').getBoundingClientRect();const h=document.querySelector('[data-exhibit-drag-region]').getBoundingClientRect();return {left:r.left,top:r.top,x:h.left+100,y:h.top+12}})()");
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:beforeDrag.x,y:beforeDrag.y});
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:beforeDrag.x,y:beforeDrag.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:beforeDrag.x+100,y:beforeDrag.y-80,button:'left',buttons:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:beforeDrag.x+100,y:beforeDrag.y-80,button:'left',clickCount:1});
  await waitFor(`(()=>{const r=document.querySelector('[data-exhibit-preview]').getBoundingClientRect();return Math.abs(r.left-${beforeDrag.left+100})<2&&Math.abs(r.top-${beforeDrag.top-80})<2})()`,'dragging title bar moves table window');
  await screenshot('paper-reader-table2-dragged.png');
  await evaluate("document.querySelector('[data-exhibit-drag-handle]').focus()");
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
  await waitFor(`Math.abs(document.querySelector('[data-exhibit-preview]').getBoundingClientRect().left-${beforeDrag.left+110})<2`,'keyboard moves focused table handle without changing paragraph');
  const handlePosition = await evaluate("(()=>{const r=document.querySelector('[data-exhibit-drag-region]').getBoundingClientRect();return {x:r.left+50,y:r.top+12}})()");
  await send('Input.dispatchMouseEvent',{type:'mousePressed',...handlePosition,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:handlePosition.x+4000,y:handlePosition.y+4000,button:'left',buttons:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:handlePosition.x+4000,y:handlePosition.y+4000,button:'left',clickCount:1});
  await waitFor("(()=>{const r=document.querySelector('[data-exhibit-preview]').getBoundingClientRect();return r.left>=15&&r.top>=15&&r.right<=innerWidth-15&&r.bottom<=innerHeight-15})()",'dragged table is bounded within viewport');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await waitFor("(()=>{const r=document.querySelector('[data-exhibit-preview]').getBoundingClientRect();return r.left>=0&&r.top>=0&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1})()",'desktop dragged position clamps after mobile resize');
  const touchHandle = await evaluate("(()=>{const r=document.querySelector('[data-exhibit-drag-region]').getBoundingClientRect();return {x:r.left+80,y:r.top+12}})()");
  const touchTop = await evaluate("document.querySelector('[data-exhibit-preview]').getBoundingClientRect().top");
  await send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{...touchHandle,id:0}]});
  await send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:touchHandle.x,y:touchHandle.y-30,id:0}]});
  await send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await waitFor(`document.querySelector('[data-exhibit-preview]').getBoundingClientRect().top<${touchTop-10}`,'mobile touch dragging moves table window');
  await evaluate("document.querySelector('button[aria-label=\"將圖表視窗置中\"]').click()");
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
  await evaluate("[...document.querySelectorAll('[data-exhibit-preview] button')].find(button=>button.innerText.includes('關閉，繼續閱讀')).click()");
  await waitFor("!document.querySelector('[data-exhibit-preview]')",'closing native table preview retains paragraph');
  await waitFor(`localStorage.getItem('paper-focus-reader:v1:paper-01')===${JSON.stringify(unchangedBeforePreview)}`,'preview and modal arrow key preserve reading state, notes and bookmarks');
  await evaluate("document.querySelector('[data-exhibit-mention=\"paper-01-table-2\"]').click()");
  await waitFor("!!document.querySelector('[data-exhibit-preview]')",'translated table label opens preview');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await waitFor("(()=>{const r=document.querySelector('[data-exhibit-preview]')?.getBoundingClientRect();return r&&r.left>=0&&r.right<=innerWidth&&r.height<=innerHeight})()",'table preview fits mobile viewport');
  await evaluate("document.querySelector('button[aria-label=\"放大圖表\"]').click()");
  await waitFor("document.querySelector('[data-exhibit-preview]')?.innerText.includes('125%')",'mobile table supports zoom and scrolling');
  await screenshot('paper-reader-table2-inline-mobile.png');
  await evaluate("[...document.querySelectorAll('[data-exhibit-preview] button')].find(button=>button.innerText.includes('關閉，繼續閱讀')).click()");
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await evaluate(`localStorage.removeItem(${JSON.stringify(spotFixture.key)})`);
  await evaluate("document.querySelector('button[aria-label=\"回到論文書庫\"]').click()");
  await waitFor("document.querySelectorAll('article').length===8",'return after cross-page and table preview tests');
  const cleanupFixture = await evaluate(`(async () => {
    const paper=await (await fetch('/data/paper-03.json')).json();
    const removed=paper.segments.find(entry=>entry.excluded&&entry.sourceText==='Declarations');
    if(!removed)throw new Error('Expected heading cleanup is missing');
    const included=paper.segments.filter(entry=>!entry.excluded);
    const nearest=included.find(entry=>entry.order>=removed.order)??included.at(-1);
    const oldDraft=structuredClone(paper);oldDraft.segments.forEach(entry=>delete entry.excluded);
    const readerKey='paper-focus-reader:v1:paper-03';const curatorKey='paper-focus-curator:v1:paper-03';
    localStorage.setItem(curatorKey,JSON.stringify(oldDraft));
    localStorage.setItem(readerKey,JSON.stringify({version:1,paperId:paper.id,sourceSha256:paper.sourceSha256,currentSegmentId:removed.id,seen:[removed.id],bookmarks:[removed.id],understood:[removed.id],notes:{[removed.id]:'preserved archived note'}}));
    return {readerKey,curatorKey,removedId:removed.id,nearestId:nearest.id,count:included.length};
  })()`);
  await evaluate("[...document.querySelectorAll('article')[2].querySelectorAll('button')].find(button=>button.innerText.includes('開始閱讀')).click()");
  await waitFor(`document.querySelector('header')?.innerText.includes('/ '+${cleanupFixture.count})`,"old curator draft inherits new heading exclusions");
  await waitFor(`(()=>{const state=JSON.parse(localStorage.getItem(${JSON.stringify(cleanupFixture.readerKey)}));return state.currentSegmentId===${JSON.stringify(cleanupFixture.nearestId)}&&state.notes[${JSON.stringify(cleanupFixture.removedId)}]==='preserved archived note'&&state.bookmarks.includes(${JSON.stringify(cleanupFixture.removedId)})&&state.understood.includes(${JSON.stringify(cleanupFixture.removedId)})&&!state.seen.includes(${JSON.stringify(cleanupFixture.removedId)})})()`,"excluded-position migration preserves archived notes and bookmarks");
  await evaluate("document.querySelector('button[aria-label=\"開啟段落清單\"]').click()");
  await waitFor(`document.querySelectorAll('[role=dialog] nav button').length===${cleanupFixture.count}`,"excluded labels absent from reading navigation");
  await waitFor("!document.querySelector('[role=dialog] nav')?.innerText.includes('Declarations')&&!document.querySelector('[role=dialog] nav')?.innerText.includes('Table 1 Coding scheme')", "obvious headings and table names hidden");
  await screenshot("paper-reader-cleanup-navigation.png");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
  await evaluate(`(()=>{const key=${JSON.stringify(cleanupFixture.curatorKey)};const draft=JSON.parse(localStorage.getItem(key));draft.segments.find(entry=>entry.id===${JSON.stringify(cleanupFixture.removedId)}).excluded=false;localStorage.setItem(key,JSON.stringify(draft));})()`);
  await send("Page.reload",{ignoreCache:true});
  await waitFor(`document.querySelector('header')?.innerText.includes('/ '+${cleanupFixture.count+1})`,"explicit user inclusion is preserved");
  await evaluate(`(()=>{const key=${JSON.stringify(cleanupFixture.readerKey)};const state=JSON.parse(localStorage.getItem(key));state.currentSegmentId='paper-03-s-d0a9953fff51';localStorage.setItem(key,JSON.stringify(state));})()`);
  await send("Page.reload",{ignoreCache:true});
  await waitFor("document.querySelector('[data-paragraph-assessment=fragment]')?.innerText.includes('不是完整段落')", "old curator draft inherits source-backed fragment classification");
  await waitFor("document.body.innerText.includes('片段翻譯 · 舊稿待重建')", "fragment translation is not presented as a full paragraph translation");
  await evaluate("[...document.querySelectorAll('button')].find(entry=>entry.textContent.includes('片段說明 · 暫不作獨立段落解釋')).click()");
  await waitFor("document.body.innerText.includes('舊版白話稿保留在校編資料')", "fragment does not receive an independent paragraph explanation");
  await screenshot("paper-reader-semantic-fragment.png");
  await evaluate("[...document.querySelectorAll('button')].find(entry=>entry.textContent.includes('查看相接原文片段')).click()");
  await waitFor(`JSON.parse(localStorage.getItem(${JSON.stringify(cleanupFixture.readerKey)})).currentSegmentId==='paper-03-s-c36263879452'`, "adjacent fragment accessible without discarding source text");
  await evaluate(`localStorage.removeItem(${JSON.stringify(cleanupFixture.readerKey)});localStorage.removeItem(${JSON.stringify(cleanupFixture.curatorKey)});`);
  await evaluate("document.querySelector('button[aria-label=\"回到論文書庫\"]').click()");
  await waitFor("document.querySelectorAll('article').length === 8", "return from cleanup migration checks");
  const libraryPath = await screenshot("paper-reader-library-final.png");

  await evaluate(`(() => {
    const first = document.querySelector('article');
    const button = [...first.querySelectorAll('button')].find((entry) => entry.textContent.includes('校編'));
    if (!button) throw new Error('找不到校編按鈕');
    button.click();
  })()`);
  await waitFor("location.hash === '#edit:paper-01'", "curator route");
  await waitFor("document.querySelector('.pdf-page-stage canvas')?.width > 0", "curator PDF render", 25000);
  const curatorSummary = await evaluate(`({
    heading: document.querySelector('header')?.innerText,
    textareas: document.querySelectorAll('textarea').length,
    canvas: [document.querySelector('canvas').width, document.querySelector('canvas').height]
  })`);
  if (curatorSummary.textareas !== 3) throw new Error("Curator must expose exactly three editing textareas");
  const expectedDrafts = await evaluate("(async()=>{const paper=await(await fetch('/data/paper-01.json')).json();return paper.segments.filter(entry=>!entry.excluded&&entry.translation.status==='ai-draft').length})()");
  if (!curatorSummary.heading.includes(`${expectedDrafts} 段 AI 草稿`)) throw new Error("Curator metrics do not report all included AI drafts");
  const curatorPath = await screenshot("paper-reader-curator-final.png");

  await evaluate(`(() => {
    const button = [...document.querySelectorAll('button')].find((entry) => entry.textContent.includes('標為人工校訂'));
    if (!button) throw new Error('找不到校訂按鈕');
    button.click();
  })()`);
  await waitFor("document.body.innerText.includes('這一段已標記為人工校訂')", "review confirmation");
  await evaluate(`(() => {
    const button = [...document.querySelectorAll('button')].find((entry) => entry.textContent.includes('試讀'));
    if (!button) throw new Error('找不到試讀按鈕');
    button.click();
  })()`);
  await waitFor("location.hash === '#paper-01'", "reader route");
  await waitFor("document.querySelector('.pdf-page-stage canvas')?.width > 0", "reader PDF render", 25000);
  await waitFor("document.body.innerText.includes('機器人程式設計是培養幼兒')", "Traditional Chinese translation");
  const readerPath = await screenshot("paper-reader-reading-final.png");

  await evaluate(`(() => {
    const button = [...document.querySelectorAll('footer button')].find((entry) => entry.textContent.includes('下一段'));
    if (!button) throw new Error('找不到下一段按鈕');
    button.click();
  })()`);
  await waitFor("[...document.querySelectorAll('header span')].some((entry) => /^2 \\/ \\d+$/.test(entry.textContent.trim()))", "paragraph navigation");
  await waitFor("document.body.innerText.includes('運算思維（CT）是一組讓個人運用電腦科學原理')", "second-paragraph translation");
  await waitFor("document.body.innerText.includes('AI 草稿')", "AI-draft disclosure");

  await send("Emulation.setDeviceMetricsOverride", {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await waitFor("[...document.querySelectorAll('[role=tab]')].some((entry) => entry.textContent.includes('中文翻譯'))", "mobile source/translation tabs");
  await clickAt("[...document.querySelectorAll('[role=tab]')].find((entry) => entry.textContent.includes('中文翻譯'))");
  await waitFor("document.body.innerText.includes('運算思維（CT）是一組讓個人運用電腦科學原理')", "mobile translation pane");
  const mobilePath = await screenshot("paper-reader-mobile-final.png");

  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await evaluate(`(() => {
    const key = 'paper-focus-reader:v1:paper-01';
    const state = JSON.parse(localStorage.getItem(key));
    state.currentSegmentId = 'paper-01-s-ab92fc53961f';
    state.seen = [...new Set([...state.seen, state.currentSegmentId])];
    localStorage.setItem(key, JSON.stringify(state));
  })()`);
  await send("Page.reload", { ignoreCache: true });
  await delay(1000);
  await waitFor("document.body.innerText.includes('圖表共讀')", "figure-reading card");
  await waitFor("document.body.innerText.includes('正文有說明 · 1 段')", "figure explanation status");
  await waitFor("document.body.innerText.includes('論文內的解釋')", "linked paper explanation");
  await waitFor("document.querySelector('.pdf-page-stage canvas')?.width > 0", "figure PDF focus", 25000);
  const figurePath = await screenshot("paper-reader-figure-reading-final.png");

  await evaluate(`(() => {
    const button = [...document.querySelectorAll('button')].find((entry) => entry.textContent.includes('閱讀這段'));
    if (!button) throw new Error('找不到圖表說明段落按鈕');
    button.click();
  })()`);
  await waitFor("document.body.innerText.includes('目前這一段就是論文對「圖 2」的說明')", "figure explanation navigation");

  await waitFor("!!document.querySelector('section[aria-label=\"本段參考文獻\"]')", "passage citation buttons");
  await evaluate(`(() => {
    const button = [...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].find((entry) => entry.textContent.includes('Huang (2016)'));
    if (!button) throw new Error('找不到 Huang 引用'); button.click();
  })()`);
  await waitFor("document.querySelector('[role=dialog] [data-abstract-faithful-translation]')?.innerText.includes('Java')", "complete Abstract translation, not a summary");
  await waitFor("document.querySelector('[role=dialog]')?.innerText.includes('先規劃整體，再讓子專案循序漸進')", "reference relationship uses the complete merged paragraph explanation");
  await waitFor("document.querySelector('[data-reference-abstract-card]')?.querySelectorAll('a').length===0", "Abstract is embedded, not an outbound link");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.includes('來源查核記錄')).click()");
  await waitFor("document.querySelector('[data-abstract-source-url]')?.textContent.includes('sciencepublishinggroup.com')", "publisher provenance retained as text");
  await waitFor("(()=>{const r=document.querySelector('[role=dialog]')?.getBoundingClientRect();return r&&r.width>300&&r.right<=innerWidth+1&&r.left>=0})()", "reference sheet fully visible");
  const referencePath = await screenshot("paper-reader-reference-final.png");
  await verifyReferenceReturn("desktop");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
  await waitFor("!document.querySelector('[role=dialog]')", "reference sheet close");
  await evaluate(`([...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].find(entry=>entry.textContent.includes('Capraro'))).click()`);
  await waitFor("document.querySelector('[role=dialog]')?.innerText.includes('不會根據標題')", "unavailable abstract honesty");
  await waitFor("document.querySelector('[data-abstract-retrieval-reason]')?.innerText.includes('OpenAlex')", "unavailable Abstract shows actual lookup scope and reason");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
  await waitFor("!document.querySelector('[role=dialog]')", "unavailable reference close");

  await send("Emulation.setDeviceMetricsOverride", {
    width: 390,
    height: 844,
    deviceScaleFactor: 1,
    mobile: true,
  });
  await clickAt("[...document.querySelectorAll('[role=tab]')].find((entry) => entry.textContent.includes('中文翻譯'))");
  await waitFor("document.querySelector('img[alt^=\"圖 2\"]')?.naturalWidth > 0", "mobile figure image");
  const mobileFigurePath = await screenshot("paper-reader-figure-mobile-final.png");
  await evaluate(`(() => {
    const button = [...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].find((entry) => entry.textContent.includes('Vega et al. (2012)'));
    if (!button) throw new Error('找不到手機版 Vega 引用'); button.click();
  })()`);
  await waitFor("/cupi2/i.test(document.querySelector('[role=dialog] [data-abstract-faithful-translation]')?.innerText??'')", "mobile complete Abstract translation");
  await waitFor("(()=>{const r=document.querySelector('[role=dialog]')?.getBoundingClientRect();return r&&r.width>300&&r.right<=innerWidth+1&&r.left>=0})()", "mobile sheet fits viewport");
  const mobileReferencePath = await screenshot("paper-reader-reference-mobile-final.png");
  await verifyReferenceReturn("mobile");
  await send("Emulation.setDeviceMetricsOverride", { width: 320, height: 844, deviceScaleFactor: 1, mobile: true });
  await delay(250);
  await verifyReferenceReturn("mobile-narrow");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
  await waitFor("!document.querySelector('[role=dialog]')", "mobile reference close");

  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await evaluate(`(() => {
    const key='paper-focus-reader:v1:paper-01';const state=JSON.parse(localStorage.getItem(key));
    state.currentSegmentId='paper-01-s-5dded5f2be0d';localStorage.setItem(key,JSON.stringify(state));
  })()`);
  await send("Page.reload", {ignoreCache:true});
  await waitFor("[...document.querySelectorAll('section[aria-label=\"本段參考文獻\"] button')].some(entry=>entry.textContent.includes('待辨識'))", "ambiguous citation disclosure");
  await evaluate(`([...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].find(entry=>entry.textContent.includes('Ching'))).click()`);
  await waitFor("(()=>{const text=document.querySelector('[role=dialog] [data-abstract-faithful-translation]')?.innerText??'';return /[\\u3400-\\u9fff]/.test(text)&&text.includes('22')&&text.includes('2012')&&text.includes('2021')})()", "DOI publisher Abstract faithfully translated into Chinese");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.includes('來源查核記錄')).click()");
  await waitFor("document.querySelector('[data-abstract-source-url]')?.textContent.includes('s11528-023-00841-1')", "selected publisher source retained without a hyperlink");
  const abstractTranslationPath = await screenshot("paper-reader-abstract-translation-final.png");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
  await waitFor("!document.querySelector('[role=dialog]')", "translated Abstract close");
  await evaluate(`([...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].find(entry=>entry.textContent.includes('Hsu')&&entry.textContent.includes('2018'))).click()`);
  await waitFor("(()=>{const text=document.querySelector('[role=dialog] [data-abstract-faithful-translation]')?.innerText??'';return /[\\u3400-\\u9fff]/.test(text)&&text.includes('2006')&&text.includes('2017')})()", "Hsu 2018 Abstract translated and embedded");
  await waitFor("document.querySelector('[data-reference-abstract-card]')?.querySelectorAll('a').length===0", "missing Abstract replaced with inline translation, not a link");
  const hsuAbstractPath = await screenshot("paper-reader-hsu-abstract-inline-final.png");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
  await waitFor("!document.querySelector('[role=dialog]')", "Hsu Abstract close");
  await evaluate(`([...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].find(entry=>entry.textContent.includes('待辨識'))).click()`);
  await waitFor("document.querySelector('[role=dialog]')?.innerText.includes('同作者、同年份')", "ambiguous candidate list");
  await evaluate("document.querySelector('[role=dialog] button.w-full').click()");
  await waitFor("document.querySelector('[role=dialog]')?.innerText.includes('這是候選文獻')", "candidate is not asserted as matched");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
  await waitFor("!document.querySelector('[role=dialog]')", "candidate sheet close");
  const databaseCase = await evaluate(`(async () => {
    const paper=await(await fetch('/data/paper-01.json',{cache:'no-store'})).json();
    const citation=paper.citations.find(entry=>paper.segments.some(segment=>segment.id===entry.segmentId&&!segment.excluded)&&entry.matchStatus==='matched'&&entry.referenceIds.some(id=>paper.references.some(reference=>reference.id===id&&reference.abstract.sourceType==='openalex'&&reference.abstract.faithfulZh)));
    if(!citation)throw new Error('No cited database Abstract fixture exists');
    const reference=paper.references.find(entry=>entry.id===citation.referenceIds[0]);
    const key='paper-focus-reader:v1:paper-01';const state=JSON.parse(localStorage.getItem(key));
    state.currentSegmentId=citation.segmentId;localStorage.setItem(key,JSON.stringify(state));
    return {label:citation.label,translationPrefix:reference.abstract.faithfulZh.slice(0,35)};
  })()`);
  await send("Page.reload", {ignoreCache:true});
  await waitFor(`[...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].some(entry=>entry.textContent.includes(${JSON.stringify(databaseCase.label)}))`, "database citation passage");
  await evaluate(`([...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].find(entry=>entry.textContent.includes(${JSON.stringify(databaseCase.label)}))).click()`);
  await waitFor(`document.querySelector('[data-abstract-faithful-translation]')?.innerText.includes(${JSON.stringify(databaseCase.translationPrefix)})`, "database full Chinese Abstract embedded");
  await waitFor("document.querySelector('[data-reference-abstract-card]')?.innerText.includes('OpenAlex')", "actual database source disclosed");
  await waitFor("document.querySelector('[data-reference-abstract-card]')?.querySelectorAll('a').length===0", "database Abstract is not replaced by links");
  const databaseAbstractPath=await screenshot("paper-reader-database-abstract-inline-final.png");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
  await waitFor("!document.querySelector('[role=dialog]')", "database Abstract close");
  const ericCase=await evaluate(`(async () => {
    const paper=await(await fetch('/data/paper-01.json',{cache:'no-store'})).json();
    const citation=paper.citations.find(entry=>entry.matchStatus==='matched'&&entry.referenceIds.some(id=>paper.references.some(reference=>reference.id===id&&reference.abstract.sourceType==='eric'&&reference.abstract.faithfulZh)));
    if(!citation)throw new Error('No cited ERIC Abstract fixture exists');
    const reference=paper.references.find(entry=>entry.id===citation.referenceIds[0]);
    const key='paper-focus-reader:v1:paper-01';const state=JSON.parse(localStorage.getItem(key));state.currentSegmentId=citation.segmentId;localStorage.setItem(key,JSON.stringify(state));
    return {label:citation.label,prefix:reference.abstract.faithfulZh.slice(0,35),origin:reference.abstract.abstractOrigin};
  })()`);
  await send("Page.reload",{ignoreCache:true});
  await waitFor(`[...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].some(entry=>entry.textContent.includes(${JSON.stringify(ericCase.label)}))`,"ERIC citation passage");
  await evaluate(`([...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].find(entry=>entry.textContent.includes(${JSON.stringify(ericCase.label)}))).click()`);
  await waitFor(`document.querySelector('[data-abstract-faithful-translation]')?.innerText.includes(${JSON.stringify(ericCase.prefix)})`,"ERIC complete Chinese translation embedded");
  await waitFor("document.querySelector('[data-reference-abstract-card]')?.innerText.includes('ERIC')","ERIC source disclosed");
  if(ericCase.origin!=="As Provided")await waitFor("document.querySelector('[data-reference-abstract-card]')?.innerText.includes('資料庫摘要完整翻譯')","ERIC staff or unspecified origin not presented as author Abstract");
  await waitFor("document.querySelector('[data-reference-abstract-card]')?.querySelectorAll('a').length===0","ERIC Abstract has no outbound link replacement");
  const ericAbstractPath=await screenshot("paper-reader-eric-abstract-inline-final.png");
  await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
  await waitFor("!document.querySelector('[role=dialog]')","ERIC Abstract close");
  const addedSourceScreenshots = {};
  for (const sourceCase of [
    {paperId:"paper-01",sourceType:"openaire",name:"OpenAIRE",databaseBadge:true},
    {paperId:"paper-03",sourceType:"doaj",name:"DOAJ",databaseBadge:false},
    {paperId:"paper-02",sourceType:"ebsco",name:"EBSCO",databaseBadge:true},
  ]) {
    const fixture = await evaluate(`(async () => {
      const paper=await(await fetch('/data/'+${JSON.stringify(sourceCase.paperId)}+'.json',{cache:'no-store'})).json();
      const citation=paper.citations.find(entry=>entry.referenceIds.some(id=>paper.references.some(reference=>reference.id===id&&reference.abstract.sourceType===${JSON.stringify(sourceCase.sourceType)}&&reference.abstract.faithfulZh)));
      if(!citation)throw new Error('No cited complete Abstract fixture for '+${JSON.stringify(sourceCase.name)});
      const reference=paper.references.find(entry=>citation.referenceIds.includes(entry.id)&&entry.abstract.sourceType===${JSON.stringify(sourceCase.sourceType)}&&entry.abstract.faithfulZh);
      const key='paper-focus-reader:v1:'+paper.id;const previous=localStorage.getItem(key);const state=previous?JSON.parse(previous):{version:1,paperId:paper.id};
      state.currentSegmentId=citation.segmentId;localStorage.setItem(key,JSON.stringify(state));
      return {label:citation.label,title:reference.title,ambiguous:citation.matchStatus==='ambiguous',translation:reference.abstract.faithfulZh,key,previous};
    })()`);
    await send("Page.navigate",{url:`${appUrl}?smoke=source-${sourceCase.sourceType}#${sourceCase.paperId}`});
    await waitFor(`[...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].some(entry=>entry.textContent.includes(${JSON.stringify(fixture.label)}))`,`${sourceCase.name} citation passage`);
    await evaluate(`([...document.querySelectorAll('section[aria-label="本段參考文獻"] button')].find(entry=>entry.textContent.includes(${JSON.stringify(fixture.label)}))).click()`);
    if(fixture.ambiguous){
      await waitFor("document.querySelector('[role=dialog]')?.innerText.includes('同作者、同年份')",`${sourceCase.name} ambiguous citation not forced`);
      await evaluate(`([...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.includes(${JSON.stringify(fixture.title)}))).click()`);
      await waitFor("document.querySelector('[role=dialog]')?.innerText.includes('這是候選文獻')",`${sourceCase.name} selected candidate warning retained`);
    }
    await waitFor(`document.querySelector('[data-abstract-faithful-translation]')?.textContent===${JSON.stringify(fixture.translation)}`,`${sourceCase.name} entire translation embedded`);
    await waitFor(`document.querySelector('[data-reference-abstract-card]')?.innerText.includes(${JSON.stringify(sourceCase.name)})`,`${sourceCase.name} actual source disclosed`);
    if(sourceCase.databaseBadge)await waitFor("document.querySelector('[data-reference-abstract-card]')?.innerText.includes('資料庫摘要完整翻譯')",`${sourceCase.name} database provenance badge`);
    await waitFor("document.querySelector('[data-reference-abstract-card]')?.querySelectorAll('a').length===0",`${sourceCase.name} no link replacement`);
    addedSourceScreenshots[sourceCase.sourceType]=await screenshot(`paper-reader-${sourceCase.sourceType}-abstract-inline-final.png`);
    await evaluate("[...document.querySelectorAll('[role=dialog] button')].find(entry=>entry.textContent.trim()==='Close').click()");
    await waitFor("!document.querySelector('[role=dialog]')",`${sourceCase.name} sheet close`);
    await evaluate(`(() => {const key=${JSON.stringify(fixture.key)};const previous=${JSON.stringify(fixture.previous)};if(previous===null)localStorage.removeItem(key);else localStorage.setItem(key,previous);})()`);
  }
  await send("Page.navigate", { url: `${appUrl}?smoke=cross-page#paper-02` });
  await waitFor("document.querySelectorAll('.pdf-page-stage').length === 2", "cross-page paragraph stitching", 25000);
  await waitFor("[...document.querySelectorAll('.pdf-page-stage canvas')].every((entry) => entry.width > 0)", "cross-page PDF render", 25000);
  const crossPagePath = await screenshot("paper-reader-cross-page-final.png");

  if (consoleErrors.length) throw new Error(`Browser console errors:\n${consoleErrors.join("\n")}`);
  console.log(JSON.stringify({
    library: libraryPath,
    curator: curatorPath,
    reader: readerPath,
    mobile: mobilePath,
    figure: figurePath,
    mobileFigureScreenshot: mobileFigurePath,
    crossPage: crossPagePath,
    reference: referencePath,
    mobileReference: mobileReferencePath,
    abstractTranslation: abstractTranslationPath,
    hsuAbstractInline: hsuAbstractPath,
    databaseAbstractInline: databaseAbstractPath,
    ericAbstractInline: ericAbstractPath,
    addedSourceAbstractsInline: addedSourceScreenshots,
    curatorSummary,
    navigation: "passed",
    paper01CrossPageParagraphMerge: "passed",
    nativePdfAndTranslatedTablePreview: "passed",
    tablePreviewPreservesProgressAndNotes: "passed",
    tableWindowMouseTouchKeyboardDragAndResize: "passed",
    allSixExhibitInterruptedParagraphsAndResumeMigration: "passed",
    allTenTablesWholeUnitsAndNextStepSkipsArchivedCells: "passed",
    conservativeReadingCleanupAndNoteMigration: "passed",
    sourceBackedFragmentClassificationAndExplanationGuard: "passed",
    aiDraftDisclosure: "passed",
    mobileTabs: "passed",
    figureReading: "passed",
    figureExplanationNavigation: "passed",
    mobileFigure: "passed",
    crossPageStitching: "passed",
    sourcedReferenceSummary: "passed",
    referenceRelationship: "passed",
    referenceReturnDesktopAndMobile: "passed",
    mobileReferenceSheet: "passed",
    missingAbstractHonesty: "passed",
    ambiguousCitationSafety: "passed",
    completeChineseAbstractTranslation: "passed",
    hsuAbstractInlineNoHyperlink: "passed",
    consoleErrors: 0,
  }, null, 2));
  } finally {
    page?.close();
    await browser.send("Target.disposeBrowserContext", { browserContextId }).catch(() => undefined);
    browser.close();
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : error);
  process.exitCode = 1;
});
