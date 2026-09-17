#!/usr/bin/env node
/** Resume all-source lookup, full local translation and auditable embedding. */
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const project=path.resolve(import.meta.dirname,"..");
const args=process.argv.slice(2);
if(args.some(value=>value!=="--offline"))throw new Error("Usage: node scripts/complete_reference_abstracts.mjs [--offline]");
function run(command, parameters) {
  return new Promise((resolve,reject)=>{
    const child=spawn(command,parameters,{cwd:project,stdio:"inherit",env:process.env});
    child.once("error",reject);
    child.once("close",(code,signal)=>{if(signal)reject(new Error(`${command} interrupted by ${signal}`));else resolve(code??1);});
  });
}
async function required(command,parameters){const code=await run(command,parameters);if(code!==0)throw new Error(`${command} ${parameters.join(" ")}: exit ${code}; successful checkpoints preserved`);}
async function main(){
  await required("python3",["scripts/build_references.py"]);
  if(!args.includes("--offline")){
    const lookups=[
      ["scripts/resolve_reference_dois.py"],
      ["scripts/build_references.py","--fetch-abstracts"],
      ["scripts/fetch_publisher_abstracts.py","--missing-only"],
      ["scripts/build_references.py"],
      ["scripts/fetch_database_abstracts.py"],
      ["scripts/fetch_semantic_scholar_abstracts.py"],
      ["scripts/fetch_europe_pmc_abstracts.py"],
      ["scripts/fetch_eric_abstracts.py"],
      ["scripts/fetch_openaire_abstracts.py","--retry-errors"],
      ["scripts/fetch_doaj_abstracts.py","--retry-errors"],
      ["scripts/fetch_ebsco_abstracts.py","--retry-errors"],
      ["scripts/fetch_curated_reference_abstracts.py"],
    ];
    for(const parameters of lookups){
      const code=await run("python3",parameters);
      if(code!==0)console.warn(`${parameters[0]} left unresolved sources; continue using verified successful caches.`);
    }
    await required(process.execPath,["scripts/translate_reference_abstracts.mjs"]);
  }
  await required("python3",["scripts/build_references.py"]);
  await required("python3",["scripts/validate_phase_a.py"]);
  await required("python3",["scripts/audit_reference_abstracts.py"]);
  const report=JSON.parse(await readFile(path.join(project,"public/data/reference-abstract-audit.json"),"utf8"));
  const {translated,references,translationPending,identityConflict,sourceUnavailable}=report.totals;
  console.log(`Embedded complete translations: ${translated}/${references}. Pending translation: ${translationPending}; identity conflicts: ${identityConflict}; source unavailable: ${sourceUnavailable}.`);
  // A partial source inventory is not reported as a fully completed task.
  if(translated!==references)process.exitCode=2;
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
