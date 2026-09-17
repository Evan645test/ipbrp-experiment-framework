#!/usr/bin/env node
/** Browser checks in a disposable context, leaving the user's reader untouched. */
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
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
 await page.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});

 const doc="document.querySelector('iframe').contentDocument";
 for(let n=2;n<=8;n++){
  const pid=`paper-${String(n).padStart(2,'0')}`;
  await page.send('Page.navigate',{url:origin+`?guide-alignment=${n}#guide:${pid}`});
  await delay(400);
  await wait(`document.querySelector('[data-guide-screen="${pid}"] iframe')?.contentDocument?.querySelectorAll('.discussion-card').length===4`,pid+' loaded');
  const checks=await evaluate(`(()=>{const d=${doc};return{answers:d.querySelectorAll('.assignment-card').length,questions:d.querySelectorAll('.reader-question-card').length,closed:d.querySelectorAll('.assignment-card[open],.reader-question-card[open]').length,order:[...d.querySelectorAll('main>section')].map(s=>s.id),width:d.documentElement.scrollWidth,viewport:d.defaultView.innerWidth};})()`);
  assert.equal(checks.answers,8);assert.equal(checks.questions,6);assert.equal(checks.closed,0);
  assert.deepEqual(checks.order,['literatureInterpretationSection','glossarySection','researchGapSection','discussionSection','assignmentSection','readerQuestionsSection','mapSection','easyReadSection']);
  assert.ok(checks.width<=checks.viewport+1,pid+' desktop overflow');
  for(const [group,selector,total] of [['Assignments','.assignment-card',8],['ReaderQuestions','.reader-question-card',6]]){
   await evaluate(`${doc}.getElementById('expand${group}').click()`);
   assert.equal(await evaluate(`${doc}.querySelectorAll('${selector}[open]').length`),total,pid+' expand '+group);
   await evaluate(`${doc}.getElementById('collapse${group}').click()`);
   assert.equal(await evaluate(`${doc}.querySelectorAll('${selector}[open]').length`),0,pid+' collapse '+group);
   await evaluate(`${doc}.querySelector('${selector} summary').click()`);
   assert.ok(await evaluate(`${doc}.querySelector('${selector}').open`));
  }
  await evaluate(`${doc}.querySelector('.topbar a[href="#assignmentSection"]').click()`);
  await delay(600);
  assert.ok(await evaluate(`(()=>{const d=${doc},r=d.getElementById('assignmentSection').getBoundingClientRect(),h=d.querySelector('.topbar').getBoundingClientRect().bottom;return r.top>=h-2&&r.top<d.defaultView.innerHeight;})()`),pid+' navigation visible');
  await evaluate(`${doc}.querySelector('.glossary-term').click()`);
  assert.ok(await evaluate(`${doc}.querySelector('dialog').open`));
  await evaluate(`${doc}.getElementById('dialogClose').click()`);
  assert.ok(await evaluate(`!${doc}.querySelector('dialog').open`));
  const fontBefore=await evaluate(`Number(${doc}.getElementById('fontControl').value)`);
  await evaluate(`${doc}.getElementById('fontIncrease').click()`);
  assert.equal(await evaluate(`Number(${doc}.getElementById('fontControl').value)`),Math.min(28,fontBefore+1));
  await evaluate(`${doc}.getElementById('fontReset').click()`);
  await wait(`${doc}.querySelector('#diagram svg,#diagram .fallback-box')`,pid+' diagram or accessible fallback');
  await page.send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate(`${doc}.getElementById('expandAssignments').click();${doc}.getElementById('expandReaderQuestions').click()`);
  await delay(200);
  assert.ok(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1&&${doc}.documentElement.scrollWidth<=${doc}.defaultView.innerWidth+1`),pid+' mobile overflow');
  if(n===2||n===6){
   await evaluate(`${doc}.getElementById('${n===2?'assignmentSection':'researchGapSection'}').scrollIntoView()`);
   const shot=await page.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
   await writeFile(`/private/tmp/guide-alignment-${pid}-mobile.png`,Buffer.from(shot.data,'base64'));
  }
  await page.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  console.log(pid+': sections, cards, navigation, glossary, font controls, diagram and mobile layout passed.');
 }
 assert.deepEqual(errors,[]);console.log('Seven aligned guides passed in a disposable browser context.');
}finally{page?.close();try{await browser.send('Target.disposeBrowserContext',{browserContextId});}catch(error){console.error('Browser cleanup: '+error.message);}browser.close();}
