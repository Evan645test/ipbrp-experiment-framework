#!/usr/bin/env node
/** Source-hashed, resumable, local-only translation of repaired reading units. */
import { readFile, writeFile, rename, unlink } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import * as OpenCC from 'opencc-js';

const root=path.resolve(import.meta.dirname,'..');
const staged=JSON.parse(await readFile(path.join(root,'content/remaining-papers-staged.json'),'utf8'));
const cachePath=path.join(root,'content/remaining-papers-translation-cache.json');
const debug=process.env.CHROME_DEBUG_URL??'http://127.0.0.1:9222';
const origin=process.env.READER_ORIGIN??'http://localhost:5173';
const tw=OpenCC.Converter({from:'cn',to:'twp'});
const terms=[['計算思維','運算思維'],['計算思考','運算思維'],['反饋','回饋'],['認知負載','認知負荷'],['元認知','後設認知'],['定性','質性'],['定量','量化'],['基於專案的學習','專題式學習'],['認知靈活性','認知彈性']];
const sha=text=>createHash('sha256').update(text).digest('hex');
const normalize=text=>terms.reduce((value,[from,to])=>value.replaceAll(from,to),tw(String(text).trim()));
let readingOverrides={papers:{}};
try{readingOverrides=JSON.parse(await readFile(path.join(root,'content/remaining-papers-reading-overrides.json'),'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
let cache;
 try{cache=JSON.parse(await readFile(cachePath,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;cache={revision:staged.revision,papers:{}};}
async function checkpoint(){const temporary=cachePath+'.tmp';await writeFile(temporary,JSON.stringify(cache,null,2)+'\n');await rename(temporary,cachePath);}
const needsModel=Object.entries(staged.papers).some(([pid,p])=>p.remainingPaperProcessing.translationTargetIds.some(id=>{const s=p.segments.find(s=>s.id===id),t=cache.papers[pid]?.segments[id];return(t?.sourceTextSha256!==sha(s.sourceText)||!['isolated-model-clone-v1','source-grounded-manual-v1'].includes(t?.explanationMethod))&&s.kind!=='heading'&&readingOverrides.papers[pid]?.[id]?.sourceText!==s.sourceText;}));
function connection(url){
 let sequence=0;const pending=new Map();const socket=new WebSocket(url);
 const ready=new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
 socket.addEventListener('message',event=>{const m=JSON.parse(String(event.data));if(!m.id||!pending.has(m.id))return;const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);if(m.error)p.reject(new Error(m.error.message));else p.resolve(m.result);});
 return{async send(method,params={}){await ready;return new Promise((resolve,reject)=>{const id=++sequence;const timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method));},180000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});},close(){for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('CDP closed'));}pending.clear();socket.close();}};
}
const version=await(await fetch(debug+'/json/version')).json();const browser=connection(version.webSocketDebuggerUrl);
const workbench=path.join(root,'public/remaining-local-ai-workbench.html');let targetId,page,createdWorkbench=false;
try{
 await writeFile(workbench,'<!doctype html><html lang="zh-TW"><meta charset="utf-8"><title>本機論文文字處理</title><body>本機文字處理進行中。<button id="init">啟動</button></body></html>\n',{flag:'wx'});createdWorkbench=true;
 ({targetId}=await browser.send('Target.createTarget',{url:origin+'/remaining-local-ai-workbench.html'}));
 let target;
 for(let attempt=0;attempt<100;attempt++){
  target=(await(await fetch(debug+'/json/list')).json()).find(t=>t.id===targetId);
  if(target?.webSocketDebuggerUrl)break;
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 if(!target?.webSocketDebuggerUrl)throw new Error('Local workbench not available');page=connection(target.webSocketDebuggerUrl);
 async function evaluate(expression,userGesture=false){const r=await page.send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture});if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception?.description??r.exceptionDetails.text);return r.result.value;}
 for(let attempt=0;attempt<100;attempt++){if(await evaluate("document.readyState==='complete'&&!!document.querySelector('#init')"))break;await new Promise(resolve=>setTimeout(resolve,100));}
 await evaluate(`document.querySelector('#init').addEventListener('click',()=>{window.ready=(async()=>{window.translator=await Translator.create({sourceLanguage:'en',targetLanguage:'zh-TW'});if(${needsModel})window.model=await LanguageModel.create({expectedInputs:[{type:'text',languages:['en']}],expectedOutputs:[{type:'text',languages:['en']}],initialPrompts:[{role:'system',content:'Explain academic passages faithfully in plain English. Preserve every acronym, qualification, statistical number and uncertainty. Do not add facts, causal claims, recommendations or evaluation absent from the passage. Use one to three concise sentences per passage.'}]});return true;})();},{once:true});true`);
 const point=await evaluate("(()=>{const r=document.querySelector('#init').getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}})()");
 await page.send('Input.dispatchMouseEvent',{type:'mousePressed',...point,button:'left',clickCount:1});await page.send('Input.dispatchMouseEvent',{type:'mouseReleased',...point,button:'left',clickCount:1});
 await evaluate('window.ready');process.stdout.write('Local translation and explanation models ready.\n');
 async function translate(source){const text=normalize(await evaluate(`window.translator.translate(${JSON.stringify(source)})`));if(!text||(/[A-Za-z]{3}/.test(source)&&!/[\u3400-\u9fff]/u.test(text)))throw new Error('Empty/non-Chinese translation');return text;}
 const constraint={type:'array',items:{type:'object',properties:{id:{type:'string'},explanation:{type:'string'}},required:['id','explanation'],additionalProperties:false}};
 for(const [pid,paper] of Object.entries(staged.papers)){
  cache.papers[pid]??={segments:{},appendices:{}};const output=cache.papers[pid];
  const pending=paper.remainingPaperProcessing.translationTargetIds.map(id=>paper.segments.find(s=>s.id===id)).filter(s=>output.segments[s.id]?.sourceTextSha256!==sha(s.sourceText)||!['isolated-model-clone-v1','source-grounded-manual-v1'].includes(output.segments[s.id]?.explanationMethod));
  for(let offset=0;offset<pending.length;){
   const batch=[];let chars=0;
   while(offset<pending.length&&batch.length<6&&(chars+pending[offset].sourceText.length<7000||!batch.length)){const s=pending[offset++];batch.push(s);chars+=s.sourceText.length;}
   const manual=new Map(batch.filter(s=>readingOverrides.papers[pid]?.[s.id]?.sourceText===s.sourceText).map(s=>[s.id,normalize(readingOverrides.papers[pid][s.id].plainZh)]));
   const automatic=batch.filter(s=>!manual.has(s.id)&&s.kind!=='heading');
   const input=automatic.map(s=>({id:s.id,passage:s.sourceText}));
   const prompt='Explain each passage independently. Return the original id and a concise explanation. Do not combine passages or add information. Input JSON:\n'+JSON.stringify(input);
   let explanations=new Map();
   if(automatic.length)try{const raw=await evaluate(`(async()=>{const session=await window.model.clone();const timer=setTimeout(()=>session.destroy(),45000);try{return await session.prompt(${JSON.stringify(prompt)},{responseConstraint:${JSON.stringify(constraint)}});}finally{clearTimeout(timer);session.destroy();}})()`);explanations=new Map(JSON.parse(raw).map(e=>[e.id,e.explanation]));if(automatic.some(s=>!explanations.get(s.id)))throw new Error('Missing explanation');}
   catch(error){process.stderr.write('Retrying individual explanations: '+error.message+'\n');explanations=new Map();for(const s of automatic){explanations.set(s.id,await evaluate(`(async()=>{const session=await window.model.clone();const timer=setTimeout(()=>session.destroy(),45000);try{return await session.prompt(${JSON.stringify('Explain this academic passage in one to three plain-English sentences. Return only the explanation, without Markdown or JSON. Add no information:\n'+s.sourceText)});}finally{clearTimeout(timer);session.destroy();}})()`));}}
   for(const s of batch){
    const faithfulZh=await translate(s.sourceText);const explanation=String(explanations.get(s.id)??'').trim();if(/```|paper-\d\d-s-|"explanation"\s*:/i.test(explanation))throw new Error('Malformed explanation: '+s.id);
    const plainZh=manual.get(s.id)??(s.kind==='heading'?`本節主題：${faithfulZh}。`:await translate(explanation));
    output.segments[s.id]={faithfulZh,plainZh,status:'ai-draft',reviewedAt:null,generatedAt:new Date().toISOString(),generatedBy:manual.has(s.id)?'Codex source-grounded explanation with Chrome on-device faithful translation':'Chrome on-device Translator and Prompt APIs; PDF-bound reconstruction',sourceTextSha256:sha(s.sourceText),explanationMethod:manual.has(s.id)||s.kind==='heading'?'source-grounded-manual-v1':'isolated-model-clone-v1'};
    await checkpoint();
   }
   process.stdout.write(`${pid}: ${offset}/${pending.length} reading-unit translations saved.\n`);
  }
  for(const a of paper.readingQuality.appendices){
   if(output.appendices[a.exhibit.id]?.sourceTextSha256===sha(a.sourceText))continue;
   output.appendices[a.exhibit.id]={faithfulZh:await translate(a.sourceText),sourceTextSha256:sha(a.sourceText)};await checkpoint();
  }
 }
 // Taiwanese terminology is also applied to authored companion guides.
 for(const p of Object.values(staged.papers)){
  for(const e of p.exhibits)e.captionZh=normalize(e.captionZh);
  for(const s of Object.values(p.exhibitCompanion.studies)){s.summaryZh=normalize(s.summaryZh);s.guideZh=s.guideZh.map(normalize);s.limitsZh=s.limitsZh.map(normalize);}
  for(const a of p.readingQuality.appendices){a.faithfulZh=normalize(a.faithfulZh);a.guideZh=a.guideZh.map(normalize);}
 }
 const manualPath=path.join(root,'content/remaining-papers-reading-overrides.json');
 try{const manual=JSON.parse(await readFile(manualPath,'utf8'));for(const patches of Object.values(manual.papers)){for(const patch of Object.values(patches)){for(const key of ['faithfulZh','plainZh'])if(patch[key])patch[key]=normalize(patch[key]);}}await writeFile(manualPath+'.tmp',JSON.stringify(manual,null,2)+'\n');await rename(manualPath+'.tmp',manualPath);}catch(error){if(error.code!=='ENOENT')throw error;}
 const stagedPath=path.join(root,'content/remaining-papers-staged.json');await writeFile(stagedPath+'.tmp',JSON.stringify(staged,null,2)+'\n');await rename(stagedPath+'.tmp',stagedPath);
 process.stdout.write('All seven translation checkpoints complete.\n');
}finally{
 page?.close();if(targetId)await browser.send('Target.closeTarget',{targetId});browser.close();if(createdWorkbench)await unlink(workbench);
}
