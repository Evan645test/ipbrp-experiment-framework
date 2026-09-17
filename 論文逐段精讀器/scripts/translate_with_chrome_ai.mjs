#!/usr/bin/env node
/**
 * Produce resumable AI-draft translations with Chrome's on-device APIs.
 *
 * Faithful translations use the Translator API. Plain-language explanations
 * are generated in English by the Prompt API and translated to zh-TW. Output
 * is compatible with apply_review_overrides.py and is never marked reviewed.
 */

import { readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import * as OpenCC from "opencc-js";

const projectDir = path.resolve(import.meta.dirname, "..");
const dataDir = path.join(projectDir, "public", "data");
const seedPath = path.join(projectDir, "content", "review-overrides.json");
const outputPath = path.join(projectDir, "content", "full-translation-overrides.json");
const debugBase = process.env.CHROME_DEBUG_URL ?? "http://127.0.0.1:9222";
const readerOrigin = process.env.READER_ORIGIN ?? "http://localhost:5173";
const args = parseArgs(process.argv.slice(2));
const POSTPROCESS_VERSION = "opencc-twp-academic-v3";
const toTaiwanTraditional = OpenCC.Converter({ from: "cn", to: "twp" });
const academicTerms = [
  ["基於專案的學習", "專題式學習"],
  ["專案式學習", "專題式學習"],
  ["增量式專題學習", "漸進式專題學習"],
  ["增量專題學習", "漸進式專題學習"],
  ["增量 PBL", "漸進式 PBL"],
  ["增量式 PBL", "漸進式 PBL"],
  ["計算思維", "運算思維"],
  ["認知靈活性", "認知彈性"],
  ["計算機程式設計", "電腦程式設計"],
  ["定量資料", "量化資料"],
  ["近端發育區", "近側發展區"],
  ["近端發展區", "近側發展區"],
  ["認知負載", "認知負荷"],
  ["學習成果", "學習成效"],
  ["質量", "品質"],
  ["反饋", "回饋"],
  ["有效且有效", "適切且有效"],
  ["聯絡起來", "連結起來"],
  ["知識聯絡", "知識連結"],
  ["啟用兒童的近側發展區", "活化兒童的近側發展區"],
  ["潛在發育水平", "潛在發展程度"],
  ["壓倒工作記憶有限的兒童", "使工作記憶有限的兒童負荷過重"],
  ["CT 和 EF 的生長", "CT 與 EF 的發展"],
  ["定製的 PBL 設計", "經調整的 PBL 設計"],
  ["與兒童的漸進發展性質相匹配", "符合兒童漸進發展的特性"],
  ["最佳挑戰", "適切挑戰"],
  ["問題解決的背景", "問題解決情境"],
  ["CT 開發", "CT 發展"],
  ["現有知識", "既有知識"],
  ["操縱資訊", "處理資訊"],
  ["老年學生", "年長學生"],
  ["未得到探索", "尚未受到充分探討"],
  ["基於專案的增量機器人程式設計", "漸進式專題機器人程式設計"],
  ["傳統的基於專案的機器人程式設計", "傳統專題式機器人程式設計"],
  ["可解釋的見解", "可解釋的洞見"],
  ["定性理解", "質性理解"],
  ["定性和", "質性與"],
  ["“", "「"],
  ["”", "」"],
  ["基於增量的基於專案的機器人程式設計", "漸進式專題機器人程式設計"],
];

function parseArgs(values) {
  const parsed = { paperId: null, limit: Number.MAX_SAFE_INTEGER };
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    if (value === "--paper") parsed.paperId = values[++index];
    else if (value === "--limit") parsed.limit = Number(values[++index]);
    else throw new Error(`Unknown argument: ${value}`);
  }
  if (parsed.paperId && !/^paper-\d{2}$/.test(parsed.paperId)) throw new Error("--paper must look like paper-01");
  if (!Number.isInteger(parsed.limit) || parsed.limit < 1) throw new Error("--limit must be a positive integer");
  return parsed;
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function atomicJsonWrite(filePath, value) {
  const temporary = `${filePath}.${process.pid}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temporary, filePath);
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function mapWithConcurrency(values, concurrency, operation) {
  const output = new Array(values.length);
  let nextIndex = 0;
  const workers = Array.from(
    { length: Math.min(concurrency, values.length) },
    async () => {
      while (nextIndex < values.length) {
        const index = nextIndex;
        nextIndex += 1;
        output[index] = await operation(values[index], index);
      }
    },
  );
  await Promise.all(workers);
  return output;
}

async function connect(webSocketUrl) {
  let sequence = 0;
  const pending = new Map();
  const socket = new WebSocket(webSocketUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data));
    if (!message.id || !pending.has(message.id)) return;
    const item = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) item.reject(new Error(message.error.message));
    else item.resolve(message.result);
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

async function findReaderTarget() {
  const response = await fetch(`${debugBase}/json/list`);
  if (!response.ok) throw new Error(`Chrome debug endpoint returned ${response.status}`);
  const targets = await response.json();
  const target = targets.find((entry) => entry.type === "page" && entry.url.startsWith(readerOrigin));
  if (!target?.webSocketDebuggerUrl) {
    throw new Error(`Open ${readerOrigin}/ in Chrome before running this command.`);
  }
  return target;
}

async function evaluate(connection, expression) {
  const response = await connection.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    const detail = response.exceptionDetails.exception?.description ?? response.exceptionDetails.text;
    throw new Error(detail);
  }
  return response.result.value;
}

async function trustedClick(connection, selector) {
  const point = await evaluate(connection, `(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    if (!element) throw new Error('Initialization button is missing');
    const rect = element.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  })()`);
  await connection.send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: point.x,
    y: point.y,
    button: "left",
    clickCount: 1,
  });
  await connection.send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: point.x,
    y: point.y,
    button: "left",
    clickCount: 1,
  });
}

async function initializeTranslator(connection) {
  const selector = "#paper-ai-init-translator";
  await evaluate(connection, `(() => {
    document.querySelector(${JSON.stringify(selector)})?.remove();
    const button = document.createElement('button');
    button.id = 'paper-ai-init-translator';
    button.textContent = '啟動本機繁中翻譯';
    Object.assign(button.style, {position:'fixed',left:'12px',top:'12px',zIndex:'2147483647',padding:'12px',background:'#111827',color:'white'});
    button.addEventListener('click', () => {
      window.__paperTranslatorReady = Translator.create({
        sourceLanguage: 'en',
        targetLanguage: 'zh-TW',
        monitor(monitor) {
          monitor.addEventListener('downloadprogress', (event) => {
            window.__paperTranslatorProgress = event.loaded;
          });
        }
      }).then((translator) => {
        window.__paperTranslator = translator;
        return true;
      });
    }, {once:true});
    document.body.append(button);
    return true;
  })()`);
  await trustedClick(connection, selector);
  process.stdout.write("Initializing or downloading the en → zh-TW translation pack...\n");
  await evaluate(connection, "window.__paperTranslatorReady");
  await evaluate(connection, `document.querySelector(${JSON.stringify(selector)})?.remove()`);
}

async function initializeLanguageModel(connection) {
  const selector = "#paper-ai-init-language-model";
  const systemPrompt = [
    "You explain academic writing accurately in plain English.",
    "For each passage, preserve all qualifications and uncertainty.",
    "Preserve every acronym exactly as written and never invent or shorten an acronym.",
    "Do not add facts, advice, evaluation, citations, or conclusions that are absent from the passage.",
    "Return one to three concise sentences understandable to a graduate student outside the specialty.",
  ].join(" ");
  await evaluate(connection, `(() => {
    document.querySelector(${JSON.stringify(selector)})?.remove();
    const button = document.createElement('button');
    button.id = 'paper-ai-init-language-model';
    button.textContent = '啟動本機白話說明模型';
    Object.assign(button.style, {position:'fixed',left:'12px',top:'12px',zIndex:'2147483647',padding:'12px',background:'#111827',color:'white'});
    button.addEventListener('click', () => {
      window.__paperLanguageModelReady = LanguageModel.create({
        expectedInputs: [{type:'text', languages:['en']}],
        expectedOutputs: [{type:'text', languages:['en']}],
        initialPrompts: [{role:'system', content:${JSON.stringify(systemPrompt)}}],
        monitor(monitor) {
          monitor.addEventListener('downloadprogress', (event) => {
            window.__paperLanguageModelProgress = event.loaded;
          });
        }
      }).then((session) => {
        window.__paperLanguageModel = session;
        return true;
      });
    }, {once:true});
    document.body.append(button);
    return true;
  })()`);
  await trustedClick(connection, selector);
  process.stdout.write("Initializing or downloading Chrome's on-device Prompt API model...\n");
  await evaluate(connection, "window.__paperLanguageModelReady");
  await evaluate(connection, `document.querySelector(${JSON.stringify(selector)})?.remove()`);
}

async function withRetry(label, operation, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await delay(700 * attempt);
    }
  }
  throw new Error(`${label} failed after ${attempts} attempts: ${lastError?.message ?? lastError}`);
}

function hasChinese(value) {
  return /[\u3400-\u9fff]/u.test(value);
}

function needsChinese(source) {
  if (looksLikeTableData(source)) return false;
  return (source.match(/[A-Za-z]{3,}/g) ?? []).length >= 2;
}

function normalizeOutput(value) {
  return String(value ?? "")
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
}

function taiwanize(value) {
  let output = toTaiwanTraditional(value);
  for (const [source, target] of academicTerms) output = output.replaceAll(source, target);
  return output;
}

function protectAuthorNames(value) {
  const names = [];
  const protectedText = value.replace(/\b[A-Z][A-Za-z’'\-]+\s+et\s+al\./g, (match) => {
    const token = `ZXQAUTHOR${names.length}QXZ`;
    names.push(match);
    return token;
  });
  return { protectedText, names };
}

function restoreAuthorNames(value, names) {
  let output = value;
  names.forEach((name, index) => {
    const token = `ZXQAUTHOR${index}QXZ`;
    output = output.replace(new RegExp(token, "giu"), name);
  });
  return output;
}

function hasAuthorPlaceholder(value) {
  return /ZXQAUTHOR\d+QXZ/iu.test(value);
}

async function translate(connection, source, label) {
  const { protectedText, names } = protectAuthorNames(source);
  const output = restoreAuthorNames(taiwanize(normalizeOutput(await withRetry(label, () =>
    evaluate(connection, `window.__paperTranslator.translate(${JSON.stringify(protectedText)})`),
  ))), names);
  if (!output) throw new Error(`${label}: translator returned an empty string`);
  if (needsChinese(source) && !hasChinese(output)) throw new Error(`${label}: translation contains no Chinese text`);
  return output;
}

async function explainInEnglish(connection, source, label) {
  const prompt = `Explain this passage without adding information:\n\n${source}`;
  const output = normalizeOutput(await withRetry(label, () =>
    evaluate(connection, `window.__paperLanguageModel.prompt(${JSON.stringify(prompt)})`),
  ));
  if (!output) throw new Error(`${label}: language model returned an empty explanation`);
  return output;
}

async function explainBatchInEnglish(connection, entries, label) {
  if (entries.length === 1) {
    return new Map([[entries[0].segment.id, await explainInEnglish(connection, entries[0].segment.sourceText, label)]]);
  }
  const input = entries.map(({ segment }) => ({ id: segment.id, passage: segment.sourceText }));
  const prompt = [
    "Explain each passage independently in one to three concise plain-English sentences.",
    "Preserve qualifications and every acronym exactly. Do not add facts or combine passages.",
    `Input JSON:\n${JSON.stringify(input)}`,
  ].join("\n\n");
  const responseConstraint = {
    type: "array",
    items: {
      type: "object",
      properties: {
        id: { type: "string" },
        explanation: { type: "string" },
      },
      required: ["id", "explanation"],
      additionalProperties: false,
    },
  };
  try {
    const raw = normalizeOutput(await withRetry(label, () =>
      evaluate(
        connection,
        `window.__paperLanguageModel.prompt(${JSON.stringify(prompt)}, {responseConstraint:${JSON.stringify(responseConstraint)}})`,
      ),
    ));
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) throw new Error("batch explanation is not an array");
    const mapped = new Map(parsed.map((item) => [item.id, normalizeOutput(item.explanation)]));
    for (const { segment } of entries) {
      if (!mapped.get(segment.id)) throw new Error(`batch omitted ${segment.id}`);
    }
    return mapped;
  } catch (error) {
    process.stderr.write(`${label}: structured batch failed; falling back to individual prompts (${error.message})\n`);
    const mapped = new Map();
    for (const { segment } of entries) {
      mapped.set(
        segment.id,
        await explainInEnglish(connection, segment.sourceText, `${label}/${segment.id}`),
      );
    }
    return mapped;
  }
}

function translationBatches(entries) {
  const batches = [];
  let current = [];
  let characters = 0;
  for (const entry of entries) {
    const size = entry.segment.sourceText.length;
    if (current.length && (current.length >= 8 || characters + size > 8000)) {
      batches.push(current);
      current = [];
      characters = 0;
    }
    current.push(entry);
    characters += size;
  }
  if (current.length) batches.push(current);
  return batches;
}

function strictCaption(source) {
  return /^(?:fig(?:ure)?\.?|table)\s*\d+\s*[.:|]/i.test(source.trim()) && source.length <= 240;
}

function looksLikeTableData(source) {
  const digits = (source.match(/\d/g) ?? []).length;
  const letters = (source.match(/[A-Za-z]/g) ?? []).length;
  const sentences = (source.match(/[.!?](?:\s|$)/g) ?? []).length;
  const tokens = source.trim().split(/\s+/u).filter(Boolean);
  const acronymTokens = tokens.filter((token) => /^[A-Z][A-Z0-9-]*[.:|]?$/u.test(token));
  const numericRow = digits >= 6 && digits >= letters * 0.6 && sentences === 0;
  const acronymHeader = tokens.length >= 2
    && acronymTokens.length / tokens.length >= 0.75
    && sentences === 0;
  return numericRow || acronymHeader;
}

function headingExplanation(faithfulZh) {
  const clean = faithfulZh.replace(/[.。：:]+$/u, "");
  return `本節主題：${clean}。`;
}

function captionExplanation(faithfulZh) {
  const clean = faithfulZh.replace(/[.。]+$/u, "");
  return `這個圖表呈現：${clean}。`;
}

function seedOutput(seed) {
  return {
    schemaVersion: "1.0.0",
    generatedAt: new Date().toISOString(),
    generator: {
      faithfulZh: "Chrome Translator API en-to-zh-TW",
      plainZh: "Chrome Prompt API plain-English then Translator API en-to-zh-TW",
      postprocessVersion: POSTPROCESS_VERSION,
      reviewPolicy: "AI drafts only; human review required",
    },
    papers: structuredClone(seed.papers ?? {}),
  };
}

async function loadOutput(seed) {
  try {
    const existing = await readJson(outputPath);
    if (existing.schemaVersion !== "1.0.0" || !existing.papers) throw new Error("invalid checkpoint schema");
    if (existing.generator?.postprocessVersion !== POSTPROCESS_VERSION) return seedOutput(seed);
    return existing;
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
    return seedOutput(seed);
  }
}

function ensurePaperOutput(output, paper) {
  const existing = output.papers[paper.id];
  if (existing && existing.sourceSha256 !== paper.sourceSha256) {
    throw new Error(`${paper.id}: checkpoint belongs to a different PDF hash`);
  }
  output.papers[paper.id] ??= { sourceSha256: paper.sourceSha256, segments: {} };
  output.papers[paper.id].segments ??= {};
  return output.papers[paper.id];
}

async function main() {
  const manifest = await readJson(path.join(dataDir, "manifest.json"));
  const seed = await readJson(seedPath);
  const output = await loadOutput(seed);
  const papers = [];
  for (const summary of manifest.papers) {
    if (args.paperId && summary.id !== args.paperId) continue;
    papers.push(await readJson(path.join(dataDir, `${summary.id}.json`)));
  }
  if (!papers.length) throw new Error("No papers matched the requested selection");

  const pending = [];
  for (const paper of papers) {
    const paperOutput = ensurePaperOutput(output, paper);
    for (const segment of paper.segments) {
      const existing = paperOutput.segments[segment.id];
      if (existing) {
        const { names } = protectAuthorNames(segment.sourceText);
        existing.faithfulZh = looksLikeTableData(segment.sourceText)
          ? segment.sourceText
          : restoreAuthorNames(existing.faithfulZh, names);
        if (hasAuthorPlaceholder(existing.faithfulZh) || hasAuthorPlaceholder(existing.plainZh)) {
          delete paperOutput.segments[segment.id];
        }
      }
      if (!paperOutput.segments[segment.id]) pending.push({ paper, segment, paperOutput });
    }
  }
  output.generatedAt = new Date().toISOString();
  await atomicJsonWrite(outputPath, output);
  if (!pending.length) {
    process.stdout.write("All selected segments already have translation drafts.\n");
    return;
  }

  const target = await findReaderTarget();
  const connection = await connect(target.webSocketDebuggerUrl);
  await connection.send("Runtime.enable");
  await initializeTranslator(connection);
  await initializeLanguageModel(connection);

  let completed = 0;
  const selected = pending.slice(0, args.limit);
  try {
    for (const batch of translationBatches(selected)) {
      const prepared = await mapWithConcurrency(batch, 4, async (entry) => {
        const { paper, segment } = entry;
        const label = `${paper.id}/${segment.order}/${segment.id}`;
        const faithfulZh = looksLikeTableData(segment.sourceText)
          ? segment.sourceText
          : await translate(connection, segment.sourceText, `${label} faithful translation`);
        return { ...entry, label, faithfulZh };
      });

      const explainable = prepared.filter(
        ({ segment }) => segment.kind !== "heading"
          && !strictCaption(segment.sourceText)
          && !looksLikeTableData(segment.sourceText),
      );
      const explanations = explainable.length
        ? await explainBatchInEnglish(
          connection,
          explainable,
          `${prepared[0].paper.id}/batch-${prepared[0].segment.order}-${prepared.at(-1).segment.order}`,
        )
        : new Map();

      const completedBatch = await mapWithConcurrency(prepared, 4, async (entry) => {
        const { segment, label, faithfulZh } = entry;
        let plainZh;
        if (segment.kind === "heading") {
          plainZh = headingExplanation(faithfulZh);
        } else if (strictCaption(segment.sourceText)) {
          plainZh = captionExplanation(faithfulZh);
        } else if (looksLikeTableData(segment.sourceText)) {
          plainZh = "此段為表格欄位或資料列，請配合原始表頭與數值閱讀。";
        } else {
          plainZh = await translate(
            connection,
            explanations.get(segment.id),
            `${label} plain explanation translation`,
          );
        }
        return { ...entry, plainZh };
      });

      for (const { segment, paperOutput, label, faithfulZh, plainZh } of completedBatch) {
        const generatedAt = new Date().toISOString();
        paperOutput.segments[segment.id] = {
          faithfulZh,
          plainZh,
          status: "ai-draft",
          reviewedAt: null,
          generatedAt,
          generatedBy: "Chrome on-device AI via Codex batch pipeline",
        };
        output.generatedAt = generatedAt;
        await atomicJsonWrite(outputPath, output);
        completed += 1;
        process.stdout.write(`[${completed}/${selected.length}] ${label}\n`);
      }
    }
  } finally {
    await evaluate(connection, "window.__paperTranslator?.destroy?.(); window.__paperLanguageModel?.destroy?.(); true").catch(() => undefined);
    connection.close();
  }

  process.stdout.write(`${JSON.stringify({ completed, remaining: pending.length - completed, output: outputPath })}\n`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack : error);
  process.exitCode = 1;
});
