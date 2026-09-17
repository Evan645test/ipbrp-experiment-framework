#!/usr/bin/env node
/** Read public Abstracts in an isolated normal browser context; never log in. */
import { readFile, writeFile, rename, readdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const project = path.resolve(import.meta.dirname, "..");
const debug = process.env.CHROME_DEBUG_URL ?? "http://localhost:9222";
const args = process.argv.slice(2);
if (args.length !== 4 || args[0] !== "--doi" || args[2] !== "--url") throw new Error("Usage: node scripts/fetch_reference_abstract_with_chrome.mjs --doi DOI --url official-source-url");
const doi = args[1].toLowerCase();
const source = new URL(args[3]);
const allowed = new Set(["doi.org", "linkinghub.elsevier.com", "scholar.lib.ntnu.edu.tw", "www.sciencedirect.com", "link.springer.com", "link.springernature.com", "www.tandfonline.com", "onlinelibrary.wiley.com", "dl.acm.org", "doi.apa.org", "psycnet.apa.org", "www.inderscience.com", "www.inderscienceonline.com", "www.cambridge.org", "arxiv.org", "jime.open.ac.uk", "ro.ecu.edu.au", "www.mdpi.com", "www.frontiersin.org", "journals.sagepub.com"]);
const authorHosts = new Set(["scholar.lib.ntnu.edu.tw", "scholars.ncu.edu.tw", "facultyprofiles.vanderbilt.edu"]);
for (const host of authorHosts) allowed.add(host);
if (source.protocol !== "https:" || !allowed.has(source.hostname)) throw new Error("Only supported official HTTPS source pages are allowed");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function connect(url) {
  const socket = new WebSocket(url);const pending = new Map();let sequence = 0;
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error("Chrome connection timed out")),10000);socket.addEventListener("open",()=>{clearTimeout(timer);resolve();},{once:true});socket.addEventListener("error",error=>{clearTimeout(timer);reject(error);},{once:true});});
  socket.addEventListener("message",({data})=>{const message=JSON.parse(String(data));const item=pending.get(message.id);if(!item)return;clearTimeout(item.timer);pending.delete(message.id);if(message.error)item.reject(new Error(message.error.message));else item.resolve(message.result);});
  socket.addEventListener("close",()=>{for(const item of pending.values()){clearTimeout(item.timer);item.reject(new Error("Chrome disconnected"));}pending.clear();});
  return {send(method,params={}){const id=++sequence;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(new Error(`${method} timed out`));},20000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});},close(){socket.close();}};
}
async function main() {
  const titles=[];
  for(const name of await readdir(path.join(project,"public/data"))){if(!/^paper-.*\.json$/.test(name))continue;const paper=JSON.parse(await readFile(path.join(project,"public/data",name),"utf8"));for(const reference of paper.references??[]){if(reference.doi===doi&&reference.identityStatus!=="title-mismatch")titles.push(reference.title);}}
  if(!titles.length)throw new Error("The DOI must be a non-mismatched local bibliography entry");
  const response=await fetch(`${debug}/json/version`);if(!response.ok)throw new Error(`Chrome endpoint: HTTP ${response.status}`);
  const browser=await connect((await response.json()).webSocketDebuggerUrl);let context;let page;
  try {
    context=(await browser.send("Target.createBrowserContext",{disposeOnDetach:true})).browserContextId;
    const {targetId}=await browser.send("Target.createTarget",{url:"about:blank",browserContextId:context});
    let target;
    for(let attempt=0;attempt<30;attempt++){target=(await(await fetch(`${debug}/json/list`)).json()).find(entry=>entry.id===targetId);if(target?.webSocketDebuggerUrl)break;await delay(100);}
    if(!target?.webSocketDebuggerUrl)throw new Error("Chrome source target was not created");
    page=await connect(target.webSocketDebuggerUrl);await page.send("Page.enable");await page.send("Page.navigate",{url:source.href});
    let result;
    for(let attempt=0;attempt<20;attempt++){
      const evaluated=await page.send("Runtime.evaluate",{returnByValue:true,expression:`(() => {
        const heading=document.querySelector('h1');
        const containers=[...document.querySelectorAll('section,.abstract,.rendering_researchoutput_abstract')];
        const section=containers.find(element=>element.querySelector('h2,h3')?.textContent.trim()==='Abstract');
        const element=document.querySelector('.abstract .textblock')??document.querySelector('#Abs1-content')??document.querySelector('.abstract.author .u-margin-s-bottom')??document.querySelector('.abstractSection,.abstract-content,blockquote.abstract')??section?.querySelector('.textblock,.c-article-section__content,.abstract');
        const text=element?.innerText?.trim()??'';
        const confirmed=[...document.querySelectorAll('a[href]')].some(link=>decodeURIComponent(link.href).toLowerCase().includes(${JSON.stringify(doi)}))||[...document.querySelectorAll('meta')].some(meta=>meta.content?.toLowerCase().includes(${JSON.stringify(doi)}));
        const title=document.querySelector('meta[name="citation_title"],meta[name="dc.Title"],meta[name="dc.title"]')?.content??heading?.innerText?.trim()??'';
        return {url:location.href,title,text,confirmed,blocked:document.body?.innerText?.slice(0,1000).match(/access denied|verify you are human|just a moment|security verification|captcha|request unsuccessful/i)!==null};
      })()`});
      result=evaluated.result?.value;
      if(result?.text&&result.confirmed)break;
      if(result?.blocked)throw new Error("Publisher requires access verification; no restriction is bypassed");
      await delay(1000);
    }
    if(!result?.text||result.text.length<40||!result.confirmed)throw new Error("Public Abstract unavailable in normal browser; no access restriction is bypassed");
    const finalUrl=new URL(result.url);if(finalUrl.protocol!=="https:"||!allowed.has(finalUrl.hostname))throw new Error("Source redirected outside supported official hosts");
    const normalize=value=>value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu," ").trim();
    if(!titles.some(title=>normalize(title)===normalize(result.title)))throw new Error("Official page title did not match the local bibliography");
    const cachePath=path.join(project,"content/reference-publisher-cache.json");let cache;
    try{cache=JSON.parse(await readFile(cachePath,"utf8"));}catch(error){if(error.code!=="ENOENT")throw error;cache={};}
    cache[doi]={status:"available",originalText:result.text,sourceUrl:result.url,sourceType:authorHosts.has(finalUrl.hostname)?"author":"publisher",metadataTitle:result.title,checkedAt:new Date().toISOString()};
    const temporary=`${cachePath}.${process.pid}.tmp`;await writeFile(temporary,`${JSON.stringify(cache,null,2)}\n`,"utf8");await rename(temporary,cachePath);
    console.log(`${doi}: verified official Abstract cached (${result.text.length} characters)`);
  } finally {page?.close();if(context)await browser.send("Target.disposeBrowserContext",{browserContextId:context}).catch(()=>{});browser.close();}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
