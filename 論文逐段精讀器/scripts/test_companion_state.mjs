#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const paper=JSON.parse(await readFile(new URL('../public/data/paper-01.json',import.meta.url),'utf8'));
const compile=text=>ts.transpileModule(text,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const url=text=>`data:text/javascript;base64,${Buffer.from(text).toString('base64')}`;
const companionUrl=url(compile(await readFile(new URL('../lib/companion-state.ts',import.meta.url),'utf8')));
const {readingSegments,resolveReadingSegment,emptyCompanionState,validateCompanionState,effectiveCompanionLinks,exhibitOverviewPassages}=await import(companionUrl);
const readerCode=compile(await readFile(new URL('../lib/reader-state.ts',import.meta.url),'utf8')).replace('"@/lib/companion-state"',JSON.stringify(companionUrl));
const {loadReaderState,emptyReaderState,storageKey,notesAsMarkdown}=await import(url(readerCode));
const storage=new Map();globalThis.window={localStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)}};
const body=readingSegments(paper);assert.equal(body.length,66);assert.ok(body.every(s=>s.kind==='body'));
const legacy=JSON.parse(await readFile(new URL('../content/paper-01-before-reading-quality.json',import.meta.url),'utf8')).paper;delete legacy.exhibitCompanion;assert.equal(readingSegments(legacy).length,101);
for(const e of paper.exhibits){
  const state=emptyReaderState(legacy);state.currentSegmentId=e.captionSegmentId;state.notes[e.captionSegmentId]='保留圖表筆記';state.bookmarks=[e.captionSegmentId];state.understood=[e.captionSegmentId];
  storage.set(storageKey(paper.id),JSON.stringify(state));
  const resumed=loadReaderState(paper);
  assert.equal(resumed.currentSegmentId,resolveReadingSegment(paper,e.captionSegmentId).id);
  assert.ok(body.some(s=>s.id===resumed.currentSegmentId));
  assert.equal(resumed.notes[e.captionSegmentId],'保留圖表筆記');assert.ok(resumed.bookmarks.includes(e.captionSegmentId));
  assert.ok(resumed.understood.includes(e.captionSegmentId));assert.ok(notesAsMarkdown(paper,resumed).includes('保留圖表筆記'));
}
const state=emptyCompanionState(paper);assert.deepEqual(validateCompanionState(state,paper),state);
const semantic=paper.exhibitCompanion.links.find(l=>l.method==='semantic'&&l.confidence==='high');
const s=paper.segments.find(s=>s.id===semantic.segmentId);
assert.ok(effectiveCompanionLinks(paper,s,state).accepted.some(l=>l.exhibitId===semantic.exhibitId));
const corrected=structuredClone(state);corrected.corrections[s.id]={[semantic.exhibitId]:'exclude'};
assert.ok(!effectiveCompanionLinks(paper,s,corrected).accepted.some(l=>l.exhibitId===semantic.exhibitId));
const candidate=paper.exhibitCompanion.links.find(l=>l.confidence==='candidate');const cs=paper.segments.find(s=>s.id===candidate.segmentId);
assert.ok(effectiveCompanionLinks(paper,cs,state).candidates.some(l=>l.exhibitId===candidate.exhibitId));
const added=structuredClone(state);added.corrections[cs.id]={[candidate.exhibitId]:'include'};
const approved=effectiveCompanionLinks(paper,cs,added);
assert.equal(approved.accepted.find(l=>l.exhibitId===candidate.exhibitId).confidence,'high');assert.ok(!approved.candidates.some(l=>l.exhibitId===candidate.exhibitId));
assert.ok(approved.accepted.find(l=>l.exhibitId===candidate.exhibitId).relationshipZh.includes('本機人工'));
for (const exhibit of paper.exhibits) {
  const passages=exhibitOverviewPassages(paper,exhibit.id,state);
  assert.deepEqual(passages.map(p=>p.segment.order),passages.map(p=>p.segment.order).toSorted((a,b)=>a-b));
  assert.ok(passages.every(p=>p.link.confidence==='high'&&p.link.evidenceQuote===p.segment.sourceText));
  assert.ok(passages.every(p=>p.label===(p.link.method==='explicit'?'明確引用':'語意關聯')));
}
assert.ok(!exhibitOverviewPassages(paper,candidate.exhibitId,state).some(p=>p.segment.id===cs.id));
assert.equal(exhibitOverviewPassages(paper,candidate.exhibitId,added).find(p=>p.segment.id===cs.id).label,'使用者加入');
assert.ok(!exhibitOverviewPassages(paper,semantic.exhibitId,corrected).some(p=>p.segment.id===s.id));
const changedPaper=structuredClone(paper);changedPaper.segments.find(p=>p.id===s.id).sourceText+=' Changed source.';
assert.ok(!exhibitOverviewPassages(changedPaper,semantic.exhibitId,state).some(p=>p.segment.id===s.id));
const edited={...s,sourceText:'Manually changed original paragraph.'};assert.equal(effectiveCompanionLinks(paper,edited,state).accepted.length,0);
assert.equal(effectiveCompanionLinks(paper,{...s,sourceText:s.sourceText+' Added authoring text.'},state).accepted.length,0);
for(const change of [v=>v.paperId='paper-02',v=>v.sourceSha256='wrong',v=>v.layout.dock='invalid',v=>v.layout.x=NaN,v=>v.layout.height=-1,v=>v.zooms[paper.exhibits[0].id]=100,v=>v.corrections.unknown={},v=>v.corrections[s.id]={unknown:'include'},v=>v.corrections[s.id]={[semantic.exhibitId]:'invalid'}]){
  const invalid=structuredClone(state);change(invalid);assert.throws(()=>validateCompanionState(invalid,paper));
}
const unlinked=structuredClone(paper);unlinked.exhibitCompanion.links=[];assert.ok(readingSegments(unlinked).some(s=>s.id===resolveReadingSegment(unlinked,paper.exhibits[0].captionSegmentId).id));
for(let i=2;i<=8;i++){const other=JSON.parse(await readFile(new URL(`../public/data/paper-0${i}.json`,import.meta.url),'utf8'));assert.equal(readingSegments(other).length,other.segments.filter(s=>!s.excluded).length);assert.ok(!other.exhibitCompanion);}
console.log('Companion state: 66 ordered body steps, all 25 old exhibit resumes, archived notes/bookmarks, candidates, corrections, stale-source guards, backup validation and seven unchanged readers passed.');
