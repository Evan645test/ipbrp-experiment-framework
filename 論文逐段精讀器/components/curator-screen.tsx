"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CheckCircle2,
  Download,
  Eye,
  FileWarning,
  GitMerge,
  Import,
  RotateCcw,
  Scissors,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { PdfFocusViewer } from "@/components/pdf-focus-viewer";
import {
  clearCuratorDraft,
  loadCuratorDraft,
  renumberSegments,
  saveCuratorDraft,
  validateCuratedPaper,
} from "@/lib/curator-state";
import { downloadText } from "@/lib/reader-state";
import type { PaperDocument, PaperSegment } from "@/lib/paper-types";

interface CuratorScreenProps {
  sourcePaper: PaperDocument;
  onBack: () => void;
  onPreview: (paper: PaperDocument) => void;
}

function draftFilename(paper: PaperDocument): string {
  return `${paper.id}-curated.json`;
}

function uniqueDerivedId(segments: PaperSegment[], base: string): string {
  const ids = new Set(segments.map((segment) => segment.id));
  let candidate = base;
  let suffix = 2;
  while (ids.has(candidate)) {
    candidate = `${base}-${suffix}`;
    suffix += 1;
  }
  return candidate;
}

function translationStatus(faithfulZh: string, plainZh: string): "untranslated" | "ai-draft" {
  return faithfulZh.trim() || plainZh.trim() ? "ai-draft" : "untranslated";
}

export function CuratorScreen({ sourcePaper, onBack, onPreview }: CuratorScreenProps) {
  const [draft, setDraft] = useState<PaperDocument>(() => loadCuratorDraft(sourcePaper));
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [notice, setNotice] = useState("");
  const sourceRef = useRef<HTMLTextAreaElement>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const currentIndex = Math.min(selectedIndex, Math.max(0, draft.segments.length - 1));
  const segment = draft.segments[currentIndex];

  useEffect(() => {
    saveCuratorDraft(draft);
  }, [draft]);

  const metrics = useMemo(() => {
    const included = draft.segments.filter((entry) => !entry.excluded);
    return {
      included: included.length,
      excluded: draft.segments.length - included.length,
      reviewed: included.filter((entry) => entry.translation.status === "reviewed").length,
      drafts: included.filter((entry) => entry.translation.status === "ai-draft").length,
    };
  }, [draft.segments]);

  function setSegments(segments: PaperSegment[], nextIndex = currentIndex) {
    setDraft((current) => ({
      ...current,
      publicationStatus: "draft",
      generatedAt: new Date().toISOString(),
      segments: renumberSegments(segments),
    }));
    setSelectedIndex(Math.min(Math.max(nextIndex, 0), Math.max(0, segments.length - 1)));
  }

  function updateCurrent(updater: (current: PaperSegment) => PaperSegment) {
    const segments = draft.segments.map((entry, index) => index === currentIndex ? updater(entry) : entry);
    setSegments(segments);
  }

  function updateSourceText(sourceText: string) {
    updateCurrent((entry) => ({
      ...entry,
      sourceText,
      reviewStatus: "needs-review",
      translation: {
        ...entry.translation,
        status: translationStatus(entry.translation.faithfulZh, entry.translation.plainZh),
        reviewedAt: null,
      },
    }));
  }

  function updateTranslation(field: "faithfulZh" | "plainZh", value: string) {
    updateCurrent((entry) => {
      const translation = { ...entry.translation, [field]: value };
      return {
        ...entry,
        reviewStatus: "needs-review",
        translation: {
          ...translation,
          status: translationStatus(translation.faithfulZh, translation.plainZh),
          reviewedAt: null,
          generatedAt: new Date().toISOString(),
          generatedBy: "local-curator",
        },
      };
    });
  }

  function markReviewed() {
    if (!segment.translation.faithfulZh.trim() || !segment.translation.plainZh.trim()) {
      setNotice("必須同時完成忠實翻譯與白話說明，才能標為人工校訂。");
      return;
    }
    updateCurrent((entry) => ({
      ...entry,
      reviewStatus: "reviewed",
      translation: {
        ...entry.translation,
        status: "reviewed",
        reviewedAt: new Date().toISOString(),
      },
    }));
    setNotice("這一段已標記為人工校訂。");
  }

  function move(direction: -1 | 1) {
    const target = currentIndex + direction;
    if (target < 0 || target >= draft.segments.length) return;
    const segments = [...draft.segments];
    [segments[currentIndex], segments[target]] = [segments[target], segments[currentIndex]];
    setSegments(segments, target);
    setNotice("已調整閱讀順序。");
  }

  function mergeNext() {
    const next = draft.segments[currentIndex + 1];
    if (!next) return;
    const merged: PaperSegment = {
      ...segment,
      id: uniqueDerivedId(draft.segments, `${segment.id}-merged`),
      sourceText: `${segment.sourceText.trim()} ${next.sourceText.trim()}`,
      fragments: [...segment.fragments, ...next.fragments],
      reviewStatus: "needs-review",
      confidence: Math.min(segment.confidence, next.confidence, 0.5),
      excluded: Boolean(segment.excluded && next.excluded),
      translation: {
        faithfulZh: [segment.translation.faithfulZh, next.translation.faithfulZh].filter(Boolean).join("\n\n"),
        plainZh: [segment.translation.plainZh, next.translation.plainZh].filter(Boolean).join("\n\n"),
        status: "ai-draft",
        reviewedAt: null,
        generatedAt: new Date().toISOString(),
        generatedBy: "local-curator",
      },
    };
    const segments = [...draft.segments];
    segments.splice(currentIndex, 2, merged);
    setSegments(segments);
    setNotice("已合併下一段；合併後內容必須重新校訂。");
  }

  function splitAtCursor() {
    const cursor = sourceRef.current?.selectionStart ?? -1;
    const text = segment.sourceText;
    if (cursor <= 0 || cursor >= text.length) {
      setNotice("請先在原文中把光標放在要切開的位置。");
      sourceRef.current?.focus();
      return;
    }
    const leftText = text.slice(0, cursor).trim();
    const rightText = text.slice(cursor).trim();
    if (!leftText || !rightText) {
      setNotice("切分點的左右兩邊都必須有文字。");
      return;
    }
    const leftId = uniqueDerivedId(draft.segments, `${segment.id}-a`);
    const rightId = uniqueDerivedId([...draft.segments, { ...segment, id: leftId }], `${segment.id}-b`);
    const blankTranslation = {
      faithfulZh: "",
      plainZh: "",
      status: "untranslated" as const,
      reviewedAt: null,
      generatedAt: new Date().toISOString(),
      generatedBy: "local-curator",
    };
    const left: PaperSegment = {
      ...segment,
      id: leftId,
      sourceText: leftText,
      reviewStatus: "needs-review",
      confidence: Math.min(segment.confidence, 0.45),
      translation: { ...blankTranslation },
    };
    const right: PaperSegment = {
      ...segment,
      id: rightId,
      sourceText: rightText,
      reviewStatus: "needs-review",
      confidence: Math.min(segment.confidence, 0.45),
      translation: { ...blankTranslation },
    };
    const segments = [...draft.segments];
    segments.splice(currentIndex, 1, left, right);
    setSegments(segments);
    setNotice("已切成兩段。因原 PDF 只有區塊座標，兩段會先共用同一個原文框。");
  }

  function toggleExcluded() {
    updateCurrent((entry) => ({ ...entry, excluded: !entry.excluded, reviewStatus: "needs-review" }));
    setNotice(segment.excluded ? "已恢復這一段。" : "已從讀者閱讀順序排除這一段。");
  }

  function exportDraft() {
    const checked = validateCuratedPaper(draft, sourcePaper);
    downloadText(draftFilename(checked), JSON.stringify(checked, null, 2), "application/json;charset=utf-8");
    setNotice("已匯出經結構驗證的校編稿。");
  }

  async function importDraft(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const checked = validateCuratedPaper(JSON.parse(await file.text()), sourcePaper);
      setDraft(checked);
      setSelectedIndex(0);
      setNotice("校編稿已匯入並通過結構驗證。");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "無法匯入校編稿。");
    }
  }

  function resetDraft() {
    if (!window.confirm("確定放棄這篇論文在瀏覽器中的校編變更？已匯出的檔案不會受影響。")) return;
    clearCuratorDraft(sourcePaper.id);
    setDraft(sourcePaper);
    setSelectedIndex(0);
    setNotice("已回復至自動擷取版本。");
  }

  return (
    <main className="reader-shell bg-[#ece9df]">
      <header className="reader-header">
        <Button type="button" variant="ghost" size="icon" onClick={onBack} aria-label="回到論文書庫">
          <ArrowLeft />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">本機校編器 · {sourcePaper.title}</p>
          <p className="mt-1 text-xs text-slate-500">
            {metrics.included} 段納入閱讀 · {metrics.reviewed} 段已校訂 · {metrics.drafts} 段 AI 草稿 · {metrics.excluded} 段排除
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => importRef.current?.click()}>
          <Import />匯入
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={exportDraft}>
          <Download />匯出
        </Button>
        <Button type="button" size="sm" onClick={() => onPreview(validateCuratedPaper(draft, sourcePaper))}>
          <Eye />試讀
        </Button>
        <input ref={importRef} type="file" accept="application/json,.json" className="sr-only" onChange={importDraft} />
      </header>

      <div className="grid min-h-0 flex-1 lg:grid-cols-[330px_minmax(0,1fr)_minmax(400px,0.9fr)]">
        <aside className="hidden min-h-0 border-r border-slate-900/10 bg-[#f8f7f2] lg:flex lg:flex-col">
          <div className="border-b border-slate-900/10 px-4 py-4">
            <p className="text-xs font-semibold tracking-[0.12em] text-slate-500">閱讀順序</p>
          </div>
          <nav className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2" aria-label="校編段落">
            {draft.segments.map((entry, index) => (
              <button
                type="button"
                key={entry.id}
                onClick={() => setSelectedIndex(index)}
                aria-current={index === currentIndex ? "step" : undefined}
                className={`mb-1 flex w-full gap-3 rounded-xl px-3 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${
                  index === currentIndex ? "bg-amber-100 text-amber-950" : "hover:bg-white"
                } ${entry.excluded ? "opacity-45" : ""}`}
              >
                <span className="w-8 shrink-0 text-xs tabular-nums text-slate-400">{String(index + 1).padStart(3, "0")}</span>
                <span className="min-w-0">
                  <span className="line-clamp-2 text-xs leading-5">{entry.sourceText}</span>
                  <span className="mt-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    {entry.excluded ? "excluded" : entry.translation.status}
                  </span>
                </span>
              </button>
            ))}
          </nav>
        </aside>

        <section className="min-h-0 min-w-0 overflow-hidden">
          <PdfFocusViewer pdfUrl={draft.pdfUrl} fragments={segment.fragments} dimOpacity={0.72} reducedMotion />
        </section>

        <section className="scrollbar-thin min-h-0 overflow-y-auto border-l border-slate-900/10 bg-[#fcfbf7] px-5 py-6 sm:px-7">
          <div className="mx-auto max-w-2xl">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Badge variant="outline">第 {currentIndex + 1} / {draft.segments.length} 段</Badge>
                <Badge variant={segment.excluded ? "destructive" : "secondary"}>
                  {segment.excluded ? "已排除" : segment.translation.status === "reviewed" ? "已校訂" : "草稿"}
                </Badge>
              </div>
              <div className="flex gap-1">
                <Button type="button" variant="ghost" size="icon-sm" onClick={() => move(-1)} disabled={currentIndex === 0} aria-label="上移一段"><ArrowUp /></Button>
                <Button type="button" variant="ghost" size="icon-sm" onClick={() => move(1)} disabled={currentIndex === draft.segments.length - 1} aria-label="下移一段"><ArrowDown /></Button>
              </div>
            </div>

            <label className="mt-5 block text-sm font-semibold" htmlFor="curator-section">章節名稱</label>
            <input
              id="curator-section"
              className="mt-2 h-10 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm outline-none focus:ring-2 focus:ring-amber-500"
              value={segment.section}
              onChange={(event) => updateCurrent((entry) => ({ ...entry, section: event.target.value, reviewStatus: "needs-review" }))}
            />

            <label className="mt-5 block text-sm font-semibold" htmlFor="curator-source">擷取原文</label>
            <Textarea
              ref={sourceRef}
              id="curator-source"
              className="mt-2 min-h-40 bg-white font-serif text-sm leading-7"
              value={segment.sourceText}
              onChange={(event) => updateSourceText(event.target.value)}
            />
            <p className="mt-2 flex items-start gap-2 text-xs leading-5 text-slate-500">
              <FileWarning className="mt-0.5 size-3.5 shrink-0 text-amber-700" />
              修改文字不會改變 PDF 座標。若在同一擷取區塊內切段，兩段會共用原文框，並必須重新校訂。
            </p>

            <div className="mt-4 grid grid-cols-2 gap-2">
              <Button type="button" variant="outline" onClick={splitAtCursor}><Scissors />從光標切段</Button>
              <Button type="button" variant="outline" onClick={mergeNext} disabled={currentIndex === draft.segments.length - 1}><GitMerge />與下一段合併</Button>
            </div>

            <label className="mt-6 block text-sm font-semibold" htmlFor="curator-faithful">忠實繁中翻譯</label>
            <Textarea
              id="curator-faithful"
              className="mt-2 min-h-40 bg-white text-base leading-8"
              value={segment.translation.faithfulZh}
              onChange={(event) => updateTranslation("faithfulZh", event.target.value)}
              placeholder="保留原文論點、限定詞與不確定性。"
            />

            <label className="mt-5 block text-sm font-semibold" htmlFor="curator-plain">白話說明</label>
            <Textarea
              id="curator-plain"
              className="mt-2 min-h-32 bg-white text-base leading-8"
              value={segment.translation.plainZh}
              onChange={(event) => updateTranslation("plainZh", event.target.value)}
              placeholder="用較容易理解的說法解釋這一段，不新增原文沒有的結論。"
            />

            <div className="mt-6 grid gap-2 border-t border-slate-900/10 pt-6 sm:grid-cols-2">
              <Button type="button" onClick={markReviewed} className="bg-emerald-700 hover:bg-emerald-800"><CheckCircle2 />標為人工校訂</Button>
              <Button type="button" variant={segment.excluded ? "secondary" : "outline"} onClick={toggleExcluded}>
                {segment.excluded ? "恢復納入閱讀" : "從閱讀順序排除"}
              </Button>
            </div>

            <Button type="button" variant="ghost" className="mt-5 w-full text-slate-500" onClick={resetDraft}>
              <RotateCcw />放棄這篇的本機校編變更
            </Button>
          </div>
        </section>
      </div>
      <output aria-live="polite" className="pointer-events-none fixed bottom-5 left-1/2 z-[70] max-w-[90vw] -translate-x-1/2 rounded-full bg-slate-950 px-4 py-2 text-center text-sm text-white shadow-xl empty:hidden">
        {notice}
      </output>
    </main>
  );
}
