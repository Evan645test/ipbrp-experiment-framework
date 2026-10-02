#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import ts from 'typescript';

const read = async path => JSON.parse(await readFile(new URL(path, import.meta.url), 'utf8'));
const compile = async path => 'data:text/javascript;base64,' + Buffer.from(ts.transpileModule(
  await readFile(new URL(path, import.meta.url), 'utf8'),
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } },
).outputText).toString('base64');
const { loadCuratorDraft, curatorStorageKey } = await import(await compile('../lib/curator-state.ts'));
const { readingSegments } = await import(await compile('../lib/companion-state.ts'));
const paper = await read('../public/data/paper-03.json');
const plan = await read('../content/paper-03-section-repairs.json');
assert.equal(createHash('sha256').update(await readFile(new URL('../public/papers/paper-03.pdf', import.meta.url))).digest('hex'), plan.sourceSha256);
const attentionId = 'paper-03-s-3d80198491e5';
const confidenceId = 'paper-03-s-24d9506c73b4';
const core = readingSegments(paper);
assert.equal(core.filter(s => s.id === attentionId).length, 1);
assert.equal(core.find(s => s.id === attentionId).section, '3.1 Attention model');
assert.equal(core.find(s => s.id === confidenceId).section, '3.3 Confidence model');
const attentionIndex = core.findIndex(s => s.id === attentionId);
assert.equal(core[attentionIndex - 1].id, 'paper-03-s-89c788a9719e');
assert.equal(core[attentionIndex + 1].id, 'paper-03-s-394f712fcaea');
assert.ok(core[attentionIndex].translation.faithfulZh.includes('注意力'));

const old = structuredClone(paper);
delete old.sectionRepairs;
for (const repair of plan.repairs) {
  const segment = old.segments.find(s => s.id === repair.segmentId);
  assert.equal(createHash('sha256').update(segment.sourceText).digest('hex'), repair.sourceTextSha256);
  segment.section = repair.previousSection;
}
const storage = new Map();
globalThis.window = { localStorage: { getItem: key => storage.get(key) ?? null } };
function migrate(draft) {
  storage.set(curatorStorageKey(paper.id), JSON.stringify(draft));
  return loadCuratorDraft(paper);
}
const migrated = migrate(old);
assert.deepEqual(migrated.segments.map(s => s.section), paper.segments.map(s => s.section));
assert.deepEqual(readingSegments(migrated).map(s => s.id), core.map(s => s.id));
for (const segment of migrated.segments) {
  const original = old.segments.find(s => s.id === segment.id);
  assert.equal(segment.sourceText, original.sourceText);
  assert.deepEqual(segment.translation, original.translation);
  assert.deepEqual(segment.fragments, original.fragments);
}

const custom = structuredClone(old);
const target = custom.segments.find(s => s.id === attentionId);
target.section = '我的注意力設計筆記';
target.translation.plainZh = '保留我自己整理的說明';
target.excluded = true;
const customResult = migrate(custom).segments.find(s => s.id === attentionId);
assert.equal(customResult.section, target.section);
assert.equal(customResult.translation.plainZh, target.translation.plainZh);
assert.equal(customResult.excluded, true);

for (const protectedField of ['source', 'position', 'review']) {
  const draft = structuredClone(old);
  const segment = draft.segments.find(s => s.id === attentionId);
  if (protectedField === 'source') segment.sourceText += ' Local source correction.';
  if (protectedField === 'position') segment.fragments[0].bbox[1] += 1;
  if (protectedField === 'review') segment.translation.status = 'reviewed';
  assert.equal(migrate(draft).segments.find(s => s.id === attentionId).section, segment.section);
}
const translationEdit = structuredClone(old);
translationEdit.segments.find(s => s.id === attentionId).translation.plainZh = '我的白話稿';
const editedResult = migrate(translationEdit).segments.find(s => s.id === attentionId);
assert.equal(editedResult.section, '3.1 Attention model');
assert.equal(editedResult.translation.plainZh, '我的白話稿');
console.log('Paper 3: Attention and Confidence restored; sequence, source and translations preserved; local edits and reviewed records protected.');
