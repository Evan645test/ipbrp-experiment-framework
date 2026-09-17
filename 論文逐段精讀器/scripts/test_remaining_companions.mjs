#!/usr/bin/env node
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const read=async name=>JSON.parse(await readFile(new URL(name,import.meta.url),'utf8'));
const compile=async name=>'data:text/javascript;base64,'+Buffer.from(ts.transpileModule(await readFile(new URL(name,import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText).toString('base64');
const {loadCuratorDraft,curatorStorageKey}=await import(await compile('../lib/curator-state.ts'));
const {readingSegments,resolveReadingSegment}=await import(await compile('../lib/companion-state.ts'));
const {explanationIssues}=await import(await compile('../lib/reading-quality.ts'));
const storage=new Map();globalThis.window={localStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)}};
for(let n=2;n<=8;n++){
 const pid=`paper-${String(n).padStart(2,'0')}`,paper=await read(`../public/data/${pid}.json`),before=await read(`../content/${pid}-before-remaining-companion.json`);
 storage.set(curatorStorageKey(pid),JSON.stringify(before));const migrated=loadCuratorDraft(paper);
 assert.deepEqual(readingSegments(migrated).map(s=>s.id),readingSegments(paper).map(s=>s.id),pid);
 assert.deepEqual(migrated.segments.map(s=>s.id),paper.segments.map(s=>s.id),pid);
 for(const r of paper.readingUnitRepairs.filter(r=>r.revision==='remaining-papers-companion-v1')){
  const target=migrated.segments.find(s=>s.id===r.targetId);assert.equal(target.sourceText,paper.segments.find(s=>s.id===r.targetId).sourceText);
  for(const id of r.absorbedIds){const source=migrated.segments.find(s=>s.id===r.targetId);if(!source.excluded&&!source.readingRole)assert.equal(resolveReadingSegment(migrated,id)?.id,r.targetId);}
 }
 const repair=paper.readingUnitRepairs.find(r=>r.revision==='remaining-papers-companion-v1'&&r.absorbedIds.length);
 const edited=structuredClone(before);edited.segments.find(s=>s.id===repair.absorbedIds[0]).translation.plainZh='保留我的手動稿';storage.set(curatorStorageKey(pid),JSON.stringify(edited));
 const preserved=loadCuratorDraft(paper);assert.ok(preserved.pendingReadingUnitRepairs.includes(repair.targetId));assert.equal(preserved.segments.find(s=>s.id===repair.absorbedIds[0]).translation.plainZh,'保留我的手動稿');
 for(const s of readingSegments(paper))assert.deepEqual(explanationIssues(paper,s),[],s.id);
}
console.log('Seven papers: safe curator migrations, archived resume points, protected edits and glossary checks passed.');
