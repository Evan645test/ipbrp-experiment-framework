#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const text = await readFile(new URL('../lib/exhibit-window-position.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
const { clampWindowOffset } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
const size = { width: 1100, height: 400 };
const viewport = { width: 1440, height: 1000 };
assert.deepEqual(clampWindowOffset({ x: 100, y: -80 }, size, viewport), { x: 100, y: -80 });
assert.deepEqual(clampWindowOffset({ x: 9000, y: -9000 }, size, viewport), { x: 154, y: -284 });
assert.deepEqual(clampWindowOffset({ x: 100, y: 100 }, { width: 358, height: 760 }, { width: 390, height: 844 }), { x: 0, y: 26 });
assert.deepEqual(clampWindowOffset({ x: NaN, y: Infinity }, size, viewport), { x: 0, y: 0 });
assert.deepEqual(clampWindowOffset({ x: -100, y: 100 }, size, { width: 320, height: 400 }), { x: 0, y: 0 });
console.log('Floating exhibit position: free movement, boundary clamps, mobile resize and invalid offsets passed.');
