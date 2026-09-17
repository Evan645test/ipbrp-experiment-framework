#!/usr/bin/env node
/** Faithfully translate complete cached Abstracts, without summary generation. */
import { createHash } from "node:crypto";
import { readFile, writeFile, rename } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import * as OpenCC from "opencc-js";

const project = path.resolve(import.meta.dirname, "..");
const outputPath = path.join(project, "content/reference-abstract-translations.json");
const origin = process.env.READER_ORIGIN ?? "http://localhost:5173";
const debug = process.env.CHROME_DEBUG_URL ?? "http://localhost:9222";
const traditional = OpenCC.Converter({ from: "cn", to: "twp" });
const args = process.argv.slice(2);
const requested = [];
let refresh=false;
for (let index = 0; index < args.length; index += 1) {
  if(args[index]==="--refresh"){refresh=true;continue;}
  if (args[index] !== "--doi" || !args[index + 1]) throw new Error("Usage: node scripts/translate_reference_abstracts.mjs [--doi DOI ...] [--refresh]");
  requested.push(args[++index].toLowerCase());
}
async function readOptional(file) {
  try { return JSON.parse(await readFile(file, "utf8")); }
  catch (error) { if (error.code !== "ENOENT") throw error; return {}; }
}
async function connect(url) {
  const socket = new WebSocket(url);
  const pending = new Map();
  let sequence = 0;
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", ({ data }) => {
    const message = JSON.parse(String(data));
    const item = pending.get(message.id);
    if (!item) return;
    clearTimeout(item.timer); pending.delete(message.id);
    if (message.error) item.reject(new Error(message.error.message)); else item.resolve(message.result);
  });
  socket.addEventListener("close", () => { for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new Error("Chrome disconnected")); } pending.clear(); });
  return {
    send(method, params = {}) {
      const id = ++sequence;
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out`)); }, 180000);
        pending.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }));
      });
    },
    close() { socket.close(); },
  };
}
async function evaluate(connection, expression) {
  const result = await connection.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text);
  return result.result.value;
}
async function main() {
  const sources = await readOptional(path.join(project, "content/reference-metadata-cache.json"));
  for (const [doi, entry] of Object.entries(await readOptional(path.join(project, "content/reference-publisher-cache.json")))) {
    if (entry.status === "available") sources[doi] = entry;
  }
  for (const [key, entry] of Object.entries(await readOptional(path.join(project, "content/reference-database-cache.json")))) {
    if (entry.status === "available" && sources[key]?.status !== "available") sources[key] = entry;
  }
  const output = await readOptional(outputPath);
  if (requested.some((doi) => sources[doi]?.status !== "available")) throw new Error("A requested DOI lacks a verified, complete source Abstract; fetch its publisher Abstract first.");
  const pending = Object.entries(sources).filter(([doi, entry]) => entry.status === "available" && entry.originalText && (!requested.length || requested.includes(doi)))
    .map(([doi, entry]) => ({ doi, entry, sha: createHash("sha256").update(entry.originalText).digest("hex") }))
    .filter(({ doi, sha }) => refresh || output[doi]?.sourceSha256 !== sha || !output[doi]?.faithfulZh);
  if (!pending.length) { console.log("No pending complete Abstract translations."); return; }
  const versionResponse=await fetch(`${debug}/json/version`,{signal:AbortSignal.timeout(10000)});
  if(!versionResponse.ok)throw new Error(`Chrome debug endpoint: HTTP ${versionResponse.status}`);
  const browser=await connect((await versionResponse.json()).webSocketDebuggerUrl);
  let connection;
  let targetId;
  try {
    // Use a dedicated normal-profile document: language packs remain available,
    // while reader state and isolated smoke-test tabs are never touched.
    ({targetId}=await browser.send("Target.createTarget",{url:`${origin}/tools/abstract-translator.html`,background:true}));
    let target;
    for(let attempt=0;attempt<40;attempt++){
      target=(await(await fetch(`${debug}/json/list`,{signal:AbortSignal.timeout(10000)})).json()).find(entry=>entry.id===targetId);
      if(target?.webSocketDebuggerUrl)break;
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    if(!target?.webSocketDebuggerUrl)throw new Error("Dedicated local Translator target was not created");
    connection=await connect(target.webSocketDebuggerUrl);
    let ready=false;
    for(let attempt=0;attempt<50;attempt++){
      ready=await evaluate(connection,"!!document.body&&location.pathname==='/tools/abstract-translator.html'&&document.title==='本機摘要翻譯作業'&&document.readyState!=='loading'");
      if(ready)break;
      await new Promise(resolve=>setTimeout(resolve,100));
    }
    if(!ready)throw new Error(`Translator document unavailable; start the local reader at ${origin}`);
    const point = await evaluate(connection, `(() => {
      if(typeof Translator==='undefined')throw new Error('Chrome Translator API is unavailable; no cloud fallback is used');
      document.querySelector('#abstract-translation-init')?.remove();
      const button=document.createElement('button');button.id='abstract-translation-init';button.textContent='啟動摘要忠實翻譯';
      Object.assign(button.style,{position:'fixed',top:'12px',left:'12px',zIndex:'2147483647',padding:'12px',background:'#111827',color:'white'});
      button.addEventListener('click',()=>{window.__abstractTranslatorReady=Translator.create({sourceLanguage:'en',targetLanguage:'zh-TW'}).then(value=>{window.__abstractTranslator=value;return true;});},{once:true});
      document.body.append(button);const r=button.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};
    })()`);
    for (const type of ["mousePressed", "mouseReleased"]) await connection.send("Input.dispatchMouseEvent", {type,...point,button:"left",clickCount:1});
    await evaluate(connection, "window.__abstractTranslatorReady");
    await evaluate(connection, "document.querySelector('#abstract-translation-init')?.remove()");
    for (const [index, { doi, entry, sha }] of pending.entries()) {
      let faithfulZh;
      let failure;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          faithfulZh = traditional(String(await evaluate(connection, `window.__abstractTranslator.translate(${JSON.stringify(entry.originalText.replace(/^Abstract\s+/i, ""))})`)).trim());
          for (const [before, after] of [["計算思維","運算思維"],["基於專案的學習","專題式學習"],["專案式學習","專題式學習"],["增量式","漸進式"],["認知靈活性","認知彈性"],["反饋","回饋"],["質量","品質"]]) faithfulZh=faithfulZh.replaceAll(before,after);
          if (!/[\u3400-\u9fff]/u.test(faithfulZh)) throw new Error("Translator returned no Chinese text");
          break;
        } catch (error) { failure=error; faithfulZh=null; }
      }
      if (!faithfulZh) throw new Error(`${doi}: ${failure?.message}`);
      output[doi] = { sourceSha256: sha, faithfulZh, sourceUrl: entry.sourceUrl, sourceType: entry.sourceType, translatedAt: new Date().toISOString(), status: "ai-draft", generator: "Chrome Translator API en-to-zh-TW; complete Abstract; no summary generation" };
      const temporary=`${outputPath}.${process.pid}.tmp`;
      await writeFile(temporary,`${JSON.stringify(output,null,2)}\n`,"utf8");await rename(temporary,outputPath);
      console.log(`${index+1}/${pending.length} ${doi}: complete Abstract translated`);
    }
  } finally {
    if(connection){
      await evaluate(connection,"document.querySelector('#abstract-translation-init')?.remove();window.__abstractTranslator?.destroy();delete window.__abstractTranslator;delete window.__abstractTranslatorReady").catch(()=>{});
      connection.close();
    }
    if(targetId)await browser.send("Target.closeTarget",{targetId}).catch(()=>{});
    browser.close();
  }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
