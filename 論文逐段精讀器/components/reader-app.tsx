"use client";

import { publicAssetUrl } from "@/lib/public-asset-url";
import NextImage from "next/image";
import {
  ChangeEvent,
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookMarked,
  BookOpenText,
  Bookmark,
  Check,
  ChevronDown,
  CircleAlert,
  FileDown,
  FileText,
  Headphones,
  Image as ImageIcon,
  Library,
  ListTree,
  LoaderCircle,
  NotebookPen,
  Pause,
  Settings2,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { PdfFocusViewer } from "@/components/pdf-focus-viewer";
import { CuratorScreen } from "@/components/curator-screen";
import { GuideScreen } from "@/components/guide-screen";
import { SegmentReferences } from "@/components/segment-references";
import { ExhibitLinkedText, ExhibitPreview } from "@/components/exhibit-preview";
import { ExhibitArchiveNotes, ExhibitCompanionWindow, ExhibitOverviewWindow, type ExhibitOverviewState } from "@/components/exhibit-companion";
import { ArchivedPassageNotes, PaperSupplements } from "@/components/paper-supplements";
import { explanationIssues } from "@/lib/reading-quality";
import { companionStorageKey, effectiveCompanionLinks, emptyCompanionState, loadCompanionState, readingSegments, resolveReadingSegment, validateCompanionState, type CompanionState } from "@/lib/companion-state";
import { loadCuratorDraft } from "@/lib/curator-state";
import {
  downloadText,
  emptyReaderState,
  loadReaderState,
  notesAsMarkdown,
  saveReaderState,
} from "@/lib/reader-state";
import type {
  PaperDocument,
  PaperExhibit,
  PaperManifest,
  PaperSegment,
  PaperSummary,
  ReaderPaperState,
  ExhibitCompanionLink,
} from "@/lib/paper-types";

type Screen = "library" | "reader" | "editor" | "guide";
type MobilePane = "source" | "translation";

function uniqueAdd(values: string[], value: string): string[] {
  return values.includes(value) ? values : [...values, value];
}

function toggleValue(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((entry) => entry !== value)
    : [...values, value];
}

function fileSafeName(title: string): string {
  const normalized = title
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9\u4e00-\u9fff]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 72);
  return normalized || "paper-notes";
}

function segmentPages(segment: PaperSegment): string {
  return [...new Set(segment.fragments.map((fragment) => fragment.page))].join("、");
}

function statusLabel(segment: PaperSegment): string {
  if (segment.translation.status === "reviewed") return "人工校訂";
  if (segment.translation.status === "ai-draft") return "AI 草稿";
  return "待翻譯";
}

function LoadingScreen({ label }: { label: string }) {
  return (
    <main className="grid min-h-screen place-items-center bg-slate-950 text-slate-100">
      <div className="text-center">
        <LoaderCircle className="mx-auto size-6 animate-spin text-amber-400" />
        <p className="mt-4 text-sm text-slate-300">{label}</p>
      </div>
    </main>
  );
}

function ErrorScreen({ message, retry }: { message: string; retry: () => void }) {
  return (
    <main className="grid min-h-screen place-items-center bg-[#f3f1eb] px-6 text-slate-950">
      <section className="max-w-lg rounded-3xl border border-red-200 bg-white p-8 shadow-xl shadow-slate-900/5">
        <CircleAlert className="size-8 text-red-600" />
        <h1 className="mt-5 font-serif text-2xl font-semibold">無法開啟閱讀資料</h1>
        <p className="mt-3 text-sm leading-7 text-slate-600">{message}</p>
        <Button className="mt-6" onClick={retry}>
          重新載入
        </Button>
      </section>
    </main>
  );
}

function ExhibitReadingCard({
  exhibit,
  paper,
  segment,
  onNavigateToSegment,
  onOpenExhibit,
}: {
  exhibit: PaperExhibit;
  paper: PaperDocument;
  segment: PaperSegment;
  onNavigateToSegment: (segmentId: string) => void;
  onOpenExhibit?: (exhibitId: string) => void;
}) {
  const label = `${exhibit.kind === "figure" ? "圖" : "表"} ${exhibit.number}`;
  const explanations = exhibit.explanationSegmentIds
    .map((id) => paper.segments.find((entry) => entry.id === id))
    .filter((entry): entry is PaperSegment => Boolean(entry && !entry.excluded && entry.paragraphAssessment?.status !== "fragment"));
  const isCaption = exhibit.captionSegmentId === segment.id;
  const isExplanation = exhibit.explanationSegmentIds.includes(segment.id);
  const imageWidth = Math.max(320, Math.round((exhibit.bbox[2] - exhibit.bbox[0]) * 2.5));
  const imageHeight = Math.max(120, Math.round((exhibit.bbox[3] - exhibit.bbox[1]) * 2.5));

  return (
    <article className="rounded-2xl border border-amber-300/70 bg-amber-50/80 p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-lg bg-amber-600 text-white">
            <ImageIcon className="size-4" />
          </span>
          <div>
            <p className="text-xs font-semibold tracking-[0.12em] text-amber-800">圖表共讀</p>
            <h3 className="font-serif text-lg font-semibold text-slate-950">{onOpenExhibit ? <button type="button" className="text-blue-700 underline underline-offset-4" data-exhibit-mention={exhibit.id} onClick={() => onOpenExhibit(exhibit.id)} aria-label={`查看 ${exhibit.label}（不離開目前段落）`}>{label} · 點選查看</button> : label}</h3>
          </div>
        </div>
        <Badge className={explanations.length ? "bg-emerald-700" : "bg-slate-600"}>
          {explanations.length ? `正文有說明 · ${explanations.length} 段` : "未找到明確正文說明"}
        </Badge>
      </div>

      <figure className="mt-4 overflow-hidden rounded-xl border border-slate-900/10 bg-white lg:hidden">
        <NextImage
          src={publicAssetUrl(exhibit.imageUrl)}
          alt={`${label}：${exhibit.captionZh || exhibit.caption}`}
          width={imageWidth}
          height={imageHeight}
          sizes="(max-width: 1023px) calc(100vw - 4rem), 1px"
          unoptimized
          className="h-auto w-full object-contain"
        />
      </figure>

      <p className="mt-4 text-sm font-medium leading-6 text-slate-800">
        {exhibit.captionZh || exhibit.caption}
      </p>
      <p className="mt-2 hidden text-xs leading-5 text-amber-900/70 lg:block">
        {onOpenExhibit ? `點選上方「${label}」可直接查看原始圖表，不離開目前段落。` : `左側已同步放大原始 ${label}，並保留 PDF 原始排版。`}
      </p>

      {isExplanation && (
        <div className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-950 ring-1 ring-emerald-200">
          目前這一段就是論文對「{label}」的說明；下方忠實翻譯與白話解釋會和圖表一起閱讀。
        </div>
      )}

      {isCaption && explanations.length > 0 && (
        <div className="mt-5 border-t border-amber-300/70 pt-4">
          <h4 className="text-sm font-semibold text-slate-950">論文內的解釋</h4>
          <div className="mt-3 space-y-3">
            {explanations.map((explanation) => (
              <div key={explanation.id} className="rounded-xl border border-slate-900/10 bg-white p-4">
                <p className="text-sm leading-7 text-slate-700">
                  {explanation.translation.faithfulZh || explanation.sourceText}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => onNavigateToSegment(explanation.id)}
                >
                  閱讀這段 <ArrowRight />
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {isCaption && explanations.length === 0 && (
        <p className="mt-4 rounded-xl bg-white px-4 py-3 text-sm leading-6 text-slate-600 ring-1 ring-slate-900/10">
          目前未在正文中找到以「{exhibit.label}」編號明確提及的說明；這篇論文在此只提供圖說或表題。
        </p>
      )}
    </article>
  );
}

function LibraryScreen({
  manifest,
  onOpen,
  onEdit,
  onGuide,
}: {
  manifest: PaperManifest;
  onOpen: (paper: PaperSummary) => void;
  onEdit: (paper: PaperSummary) => void;
  onGuide: (paper: PaperSummary) => void;
}) {
  return (
    <main className="min-h-screen bg-[#f3f1eb] text-slate-950">
      <header className="border-b border-slate-900/10 bg-[#f8f7f2]">
        <div className="mx-auto flex max-w-[1480px] items-center justify-between px-5 py-5 sm:px-10">
          <div className="flex items-center gap-3">
            <span className="grid size-10 place-items-center rounded-xl bg-slate-950 text-amber-300 shadow-lg shadow-slate-950/15">
              <BookOpenText className="size-5" />
            </span>
            <div>
              <p className="font-serif text-xl font-semibold leading-none">頁間</p>
              <p className="mt-1 text-xs tracking-[0.12em] text-slate-500">PAPER FOCUS READER</p>
            </div>
          </div>
          <Badge variant="outline" className="border-slate-300 bg-white/60 text-slate-600">
            8 篇論文 · 導讀與精讀
          </Badge>
        </div>
      </header>

      <section className="mx-auto max-w-[1480px] px-5 pb-16 pt-10 sm:px-10 sm:pt-16">
        <div className="grid gap-8 border-b border-slate-900/10 pb-10 lg:grid-cols-[1fr_420px] lg:items-end">
          <div>
            <p className="text-sm font-semibold tracking-[0.14em] text-amber-700">論文導讀 · 集中閱讀</p>
            <h1 className="mt-3 max-w-4xl font-serif text-4xl font-semibold leading-[1.12] tracking-[-0.02em] sm:text-6xl">
              從研究全貌，
              <span className="text-slate-500">讀進每一段。</span>
            </h1>
          </div>
          <p className="max-w-xl text-base leading-8 text-slate-600">
            先用互動導讀掌握研究設計與結果，再逐段對照原始 PDF、中文翻譯與圖表。兩種閱讀方式從同一個入口開啟，精讀進度、書籤與筆記保存在這台裝置。
          </p>
        </div>

        <div className="mt-8 flex items-center justify-between">
          <div>
            <h2 className="font-serif text-2xl font-semibold">選擇論文</h2>
            <p className="mt-1 text-sm text-slate-500">目前收錄 {manifest.paperCount} 篇已授權論文</p>
          </div>
          <span className="hidden items-center gap-2 text-xs text-slate-500 sm:flex">
            <ShieldCheck className="size-4 text-emerald-700" />
            原始檔案不離開本機
          </span>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {manifest.papers.map((paper) => (
            <article
              key={paper.id}
              className="group flex min-h-72 flex-col rounded-[1.4rem] border border-slate-900/10 bg-[#fcfbf7] p-6 text-left shadow-[0_12px_35px_rgb(15_23_42/5%)] transition duration-300 hover:-translate-y-1 hover:border-slate-900/25 hover:shadow-[0_20px_50px_rgb(15_23_42/10%)]"
            >
              <div className="flex items-start justify-between">
                <span className="font-serif text-4xl font-semibold text-slate-300 transition group-hover:text-amber-600">
                  {String(paper.number).padStart(2, "0")}
                </span>
                <Badge variant="secondary" className="bg-slate-100 text-slate-600">
                  草稿
                </Badge>
              </div>
              <h3 className="mt-7 line-clamp-5 font-serif text-xl font-semibold leading-7">
                {paper.title}
              </h3>
              <div className="mt-auto flex items-center justify-between border-t border-slate-900/10 pt-5 text-xs text-slate-500">
                <span>{paper.pageCount} 頁 · {paper.bodySegmentCount ?? paper.includedSegmentCount ?? paper.segmentCount} 段</span>
              </div>
              <Button type="button" variant="outline" className="mt-4 w-full" onClick={() => onGuide(paper)} aria-label={`開啟${paper.title}的互動導讀`}>
                <BookOpenText />互動導讀
              </Button>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => onEdit(paper)}>
                  <NotebookPen />校編
                </Button>
                <Button type="button" size="sm" onClick={() => onOpen(paper)}>
                  逐段精讀 <ArrowRight />
                </Button>
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

function TranslationPanel({
  paper,
  segment,
  state,
  setState,
  speaking,
  onSpeak,
  onNavigateToSegment,
  onOpenExhibit,
  companion,
}: {
  paper: PaperDocument;
  segment: PaperSegment;
  state: ReaderPaperState;
  setState: (updater: (current: ReaderPaperState) => ReaderPaperState) => void;
  speaking: boolean;
  onSpeak: (text: string, language: string) => void;
  onNavigateToSegment: (segmentId: string, restoreReference?: () => void) => void;
  onOpenExhibit?: (exhibitId: string) => void;
  companion?: {
    selected: PaperExhibit | null;
    accepted: ExhibitCompanionLink[];
    candidates: ExhibitCompanionLink[];
    collapsed: boolean;
    onCorrect: (id: string, action: "include" | "exclude" | "reset") => void;
  };
}) {
  const bookmarked = state.bookmarks.includes(segment.id);
  const understood = state.understood.includes(segment.id);
  const pages = segmentPages(segment);
  const isFragment = segment.paragraphAssessment?.status === "fragment";
  const plainIssues = explanationIssues(paper, segment);
  const relatedExhibits = (segment.exhibitIds ?? [])
    .map((id) => paper.exhibits?.find((exhibit) => exhibit.id === id))
    .filter((exhibit): exhibit is PaperExhibit => Boolean(exhibit));
  return (
    <section className="flex min-h-0 flex-1 flex-col bg-[#f8f7f2]">
      <div data-translation-scroll className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-8 lg:px-10 lg:py-9">
        <div className="mx-auto max-w-2xl">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="border-slate-300 bg-white text-slate-600">
              {segment.section}
            </Badge>
            <Badge
              variant={segment.translation.status === "reviewed" ? "default" : "secondary"}
              className={
                segment.translation.status === "reviewed"
                  ? "bg-emerald-700"
                  : "bg-amber-100 text-amber-900"
              }
            >
              {statusLabel(segment)}
            </Badge>
            <span className="text-xs text-slate-500">PDF 第 {pages} 頁</span>
          </div>

          {!companion && relatedExhibits.length > 0 && (
            <div className="mt-6 space-y-4">
              {relatedExhibits.map((exhibit) => (
                <ExhibitReadingCard
                  key={exhibit.id}
                  exhibit={exhibit}
                  paper={paper}
                  segment={segment}
                  onNavigateToSegment={onNavigateToSegment}
                  onOpenExhibit={onOpenExhibit}
                />
              ))}
            </div>
          )}

          {segment.paragraphAssessment && (
            <div className="mt-6 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm leading-7 text-amber-950" data-paragraph-assessment={segment.paragraphAssessment.status}>
              <p className="font-semibold">{isFragment ? "原文片段 · 不是完整段落，待重建" : "段落完整性待核對 · 尚未判定無效"}</p>
              {segment.paragraphAssessment.reasons.map((reason) => <p key={reason} className="mt-1">{reason}</p>)}
              {isFragment && <p className="mt-2">原文與舊翻譯保留供核對，不提供獨立段落解釋，也不直接刪除或猜測補寫缺少內容。</p>}
              <div className="mt-2 flex flex-wrap gap-2">
                {segment.paragraphAssessment.relatedSegmentIds.filter((id) => paper.segments.some((entry) => entry.id === id)).map((id) => (
                  <Button key={id} type="button" variant="outline" size="sm" onClick={() => onNavigateToSegment(id)}>查看相接原文片段<ArrowRight /></Button>
                ))}
              </div>
            </div>
          )}

          <div className="mt-7 border-t border-slate-900/10 pt-7">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-serif text-2xl font-semibold">{isFragment ? "片段翻譯 · 舊稿待重建" : "忠實翻譯"}</h2>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() =>
                  onSpeak(
                    segment.translation.faithfulZh || segment.sourceText,
                    segment.translation.faithfulZh ? "zh-TW" : "en-US",
                  )
                }
              >
                {speaking ? <Pause /> : <Headphones />}
                {speaking ? "停止朗讀" : "朗讀"}
              </Button>
            </div>
            {segment.translation.faithfulZh ? (
              <p className="mt-4 whitespace-pre-line text-lg leading-9 text-slate-900">
                <ExhibitLinkedText text={segment.translation.faithfulZh} exhibits={relatedExhibits} onOpen={onOpenExhibit} />
              </p>
            ) : (
              <div className="mt-4 rounded-2xl border border-amber-300/70 bg-amber-50 p-5 text-sm leading-7 text-amber-950">
                <div className="flex items-center gap-2 font-semibold">
                  <CircleAlert className="size-4" />
                  此段尚未完成中文翻譯
                </div>
                <p className="mt-2 text-amber-900/80">
                  這是自動切分草稿，正式閱讀前必須在校訂模式補上翻譯並人工確認。
                </p>
              </div>
            )}
          </div>

          {companion && <div className="mt-5 text-sm" data-companion-controls>
            <div className="flex flex-wrap gap-2">
              {companion.accepted.map(link => {
                const e = paper.exhibits?.find(e => e.id === link.exhibitId);
                return e && <Button key={e.id} size="sm" variant={companion.selected?.id === e.id && !companion.collapsed ? "default" : "outline"}
                  onClick={() => onOpenExhibit?.(e.id)}>{e.kind === "table" ? "表" : "圖"} {e.number} · {link.method === "explicit" ? "編號關聯" : "語意／人工關聯"}</Button>;
              })}
            </div>
            {companion.candidates.length > 0 && <details className="mt-3 rounded-xl border bg-white p-3" data-companion-candidates><summary className="cursor-pointer">待確認的語意候選（{companion.candidates.length}）</summary>
              {companion.candidates.map(link => <div key={link.exhibitId} className="mt-3 border-t pt-2"><p>{paper.exhibits?.find(e => e.id === link.exhibitId)?.label}：{link.relationshipZh}</p>
                <Button size="sm" variant="outline" onClick={() => onOpenExhibit?.(link.exhibitId)}>先看完整圖表</Button>
                <Button size="sm" variant="outline" onClick={() => companion.onCorrect(link.exhibitId, "include")}>確認加入伴讀</Button>
                <Button size="sm" variant="ghost" onClick={() => companion.onCorrect(link.exhibitId, "exclude")}>排除此候選</Button></div>)}
            </details>}
            <details className="mt-3 rounded-xl border bg-white p-3"><summary className="cursor-pointer">修正本段的圖表關聯</summary>
              <p className="mt-2 text-xs text-slate-500">只儲存在目前瀏覽器，可匯出備份；不修改共用論文資料。</p>
              {paper.exhibits?.map(e => <div key={e.id} className="mt-2 flex flex-wrap items-center gap-1"><span className="mr-auto">{e.label}</span>
                <Button size="sm" variant="ghost" onClick={() => companion.onCorrect(e.id, "include")}>加入</Button>
                <Button size="sm" variant="ghost" onClick={() => companion.onCorrect(e.id, "exclude")}>排除</Button>
                <Button size="sm" variant="ghost" onClick={() => companion.onCorrect(e.id, "reset")}>恢復預設</Button></div>)}
            </details>
          </div>}

          <Collapsible className="mt-6 rounded-2xl border border-slate-900/10 bg-white/70">
            <CollapsibleTrigger className="flex w-full items-center justify-between px-5 py-4 text-left text-sm font-semibold">
              <span>擷取的原文文字</span>
              <ChevronDown className="size-4" />
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t border-slate-900/10 px-5 py-5 font-serif text-base leading-8 text-slate-600">
              <ExhibitLinkedText text={segment.sourceText} exhibits={relatedExhibits} onOpen={onOpenExhibit} />
            </CollapsibleContent>
          </Collapsible>

          <Collapsible className="mt-7 rounded-2xl border border-slate-900/10 bg-white">
            <CollapsibleTrigger className="flex w-full items-center justify-between px-5 py-4 text-left text-sm font-semibold">
              <span>{isFragment ? "片段說明 · 暫不作獨立段落解釋" : "白話解釋"}</span>
              <ChevronDown className="size-4" />
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t border-slate-900/10 px-5 py-5 text-base leading-8 text-slate-700">
              {plainIssues.length ? <div role="alert" data-explanation-fidelity-guard>{plainIssues.map(issue => <p key={issue}>{issue}</p>)}<p className="mt-2">舊白話稿仍保留於校編資料，不在此當作已核對的段落說明。</p></div> : isFragment
                ? "此內容已確認是切分不完整的原文片段。需先找回完整原段落或條列項目，再重新翻譯及解釋；舊版白話稿保留在校編資料，不在此冒充完整段落說明。"
                : segment.translation.plainZh || "這一段的白話解釋尚未完成，發布前不會伪裝成已校訂內容。"}
            </CollapsibleContent>
          </Collapsible>

          <SegmentReferences paper={paper} segment={segment} onNavigateToSegment={onNavigateToSegment} />
          {paper.readingQuality && <ArchivedPassageNotes paper={paper} segment={segment} state={state} onState={setState} />}

          <div className="mt-8">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-serif text-xl font-semibold">
                <NotebookPen className="size-5 text-amber-700" />
                研究筆記
              </h2>
              <Button
                type="button"
                variant={bookmarked ? "secondary" : "ghost"}
                size="sm"
                onClick={() =>
                  setState((current) => ({
                    ...current,
                    bookmarks: toggleValue(current.bookmarks, segment.id),
                  }))
                }
              >
                {bookmarked ? <BookMarked /> : <Bookmark />}
                {bookmarked ? "已加書籤" : "加入書籤"}
              </Button>
            </div>
            <Textarea
              className="mt-4 min-h-32 resize-y border-slate-300 bg-white p-4 text-base leading-7"
              value={state.notes[segment.id] ?? ""}
              onChange={(event) =>
                setState((current) => ({
                  ...current,
                  notes: { ...current.notes, [segment.id]: event.target.value },
                }))
              }
              placeholder="記下這一段對你的研究有什麼意義……"
              aria-label="目前段落的研究筆記"
            />
          </div>

          <div className="mt-7 flex items-center justify-between border-t border-slate-900/10 py-6">
            <span className="text-sm text-slate-500">看過不等於理解，由你決定何時完成。</span>
            <Button
              type="button"
              variant={understood ? "default" : "outline"}
              className={understood ? "bg-emerald-700 hover:bg-emerald-800" : ""}
              onClick={() =>
                setState((current) => ({
                  ...current,
                  understood: toggleValue(current.understood, segment.id),
                }))
              }
            >
              <Check />
              {understood ? "已理解" : "標記為已理解"}
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}

function ReaderScreen({
  paper,
  onBack,
  onGuide,
}: {
  paper: PaperDocument;
  onBack: () => void;
  onGuide: () => void;
}) {
  const readingPaper = useMemo(
    () => ({ ...paper, segments: readingSegments(paper) }),
    [paper],
  );
  const [state, setRawState] = useState<ReaderPaperState>(() => emptyReaderState(readingPaper));
  const [hydrated, setHydrated] = useState(false);
  const [mobilePane, setMobilePane] = useState<MobilePane>("source");
  const [speaking, setSpeaking] = useState(false);
  const [notice, setNotice] = useState(paper.pendingReadingUnitRepairs?.length ? "部分跨頁或表格內容已有本機校編修改，已保留原稿，未自動套用合併。請於校編器核對。" : "");
  const [activeExhibitId, setActiveExhibitId] = useState<string | null>(null);
  const [companionState, setCompanionState] = useState<CompanionState>(() => emptyCompanionState(paper));
  const [openedCompanion, setOpenedCompanion] = useState<{ segmentId: string; exhibitId: string } | null>(null);
  const [collapsedCompanion, setCollapsedCompanion] = useState<string | null>(null);
  const [overviewExhibitId, setOverviewExhibitId] = useState<string | null>(null);
  const [overviewState, setOverviewState] = useState<ExhibitOverviewState>({ width: 1100, height: 750, x: 32, y: 90, mobileHeight: 300, zooms: {} });
  const [referenceHistory, setReferenceHistory] = useState<Array<{
    segmentId: string;
    restoreReference: () => void;
  }>>([]);
  const importInputRef = useRef<HTMLInputElement>(null);
  const importCompanionRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setRawState(loadReaderState(paper));
      setCompanionState(loadCompanionState(paper));
      setHydrated(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [paper]);

  useEffect(() => {
    if (!hydrated) return;
    try { saveReaderState(state); }
    catch { window.setTimeout(() => setNotice("瀏覽器無法儲存閱讀資料，請立即匯出備份；目前筆記仍在畫面記憶體中。"), 0); }
  }, [hydrated, state]);

  useEffect(() => {
    if (!hydrated || !paper.exhibitCompanion) return;
    try { window.localStorage.setItem(companionStorageKey(paper.id), JSON.stringify(companionState)); }
    catch { window.setTimeout(() => setNotice("伴讀設定無法儲存，請匯出伴讀修正備份。"), 0); }
  }, [hydrated, companionState, paper.id, paper.exhibitCompanion]);

  const setState = useCallback(
    (updater: (current: ReaderPaperState) => ReaderPaperState) => {
      setRawState((current) => ({ ...updater(current), updatedAt: new Date().toISOString() }));
    },
    [],
  );

  const currentIndex = Math.max(
    0,
    readingPaper.segments.findIndex((segment) => segment.id === state.currentSegmentId),
  );
  const segment = readingPaper.segments[currentIndex] ?? readingPaper.segments[0];
  const companionLinks = segment && paper.exhibitCompanion ? effectiveCompanionLinks(paper, segment, companionState) : { accepted: [], candidates: [] };
  const selectedCompanionId = openedCompanion?.segmentId === segment?.id ? openedCompanion.exhibitId : companionLinks.accepted[0]?.exhibitId;
  const selectedCompanion = paper.exhibits?.find(e => e.id === selectedCompanionId) ?? null;
  const companionVisible = Boolean(paper.exhibitCompanion && selectedCompanion && collapsedCompanion !== segment?.id);
  const companionExhibits = paper.exhibits?.filter(e => companionLinks.accepted.some(l => l.exhibitId === e.id) || e.id === selectedCompanionId) ?? [];
  const openExhibit = useCallback((id: string) => {
    if (paper.exhibitCompanion && segment) {
      setOpenedCompanion({ segmentId: segment.id, exhibitId: id });
      setCollapsedCompanion(null);
    } else setActiveExhibitId(id);
  }, [paper.exhibitCompanion, segment]);
  function correctCompanion(id: string, action: "include" | "exclude" | "reset") {
    if (!segment) return;
    setCompanionState(current => {
      const corrections = { ...current.corrections[segment.id] };
      if (action === "reset") delete corrections[id]; else corrections[id] = action;
      return { ...current, corrections: { ...current.corrections, [segment.id]: corrections } };
    });
    if (action === "exclude" && openedCompanion?.exhibitId === id) setOpenedCompanion(null);
    if (action === "include") openExhibit(id);
  }
  const progress = readingPaper.segments.length
    ? Math.round((state.seen.length / readingPaper.segments.length) * 100)
    : 0;

  const goTo = useCallback(
    (index: number) => {
      const next = readingPaper.segments[Math.min(Math.max(index, 0), readingPaper.segments.length - 1)];
      if (!next) return;
      setCollapsedCompanion(null);
      setState((current) => ({
        ...current,
        currentSegmentId: next.id,
        seen: uniqueAdd(current.seen, next.id),
      }));
    },
    [readingPaper.segments, setState],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (activeExhibitId || target?.closest("[role='dialog'], [data-companion-window], [data-exhibit-overview]")) return;
      if (target?.matches("input, textarea, select, [contenteditable='true']")) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        goTo(currentIndex + 1);
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goTo(currentIndex - 1);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeExhibitId, currentIndex, goTo]);

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool || !segment) return;
    const controller = new AbortController();
    const report = (error: unknown) => setNotice(error instanceof Error ? error.message : "WebMCP 操作失敗。");
    const registrations = [
      context.registerTool(
        {
          name: "navigate_to_paper_segment",
          title: "移動到論文段落",
          description: "依照一起始段落序號移動閱讀位置。",
          inputSchema: {
            type: "object",
            properties: { order: { type: "integer", minimum: 1, maximum: readingPaper.segments.length } },
            required: ["order"],
            additionalProperties: false,
          },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          execute: (input: unknown) => {
            const order = Number((input as { order?: unknown }).order);
            if (!Number.isInteger(order) || order < 1 || order > readingPaper.segments.length) {
              throw new Error("段落序號超出範圍。");
            }
            goTo(order - 1);
            return { paperId: paper.id, order, segmentId: readingPaper.segments[order - 1].id };
          },
        },
        { signal: controller.signal },
      ),
      context.registerTool(
        {
          name: "mark_current_segment_understood",
          title: "標記目前段落已理解",
          description: "將閱讀器中的目前段落標記為已理解。",
          inputSchema: { type: "object", properties: {}, additionalProperties: false },
          annotations: { readOnlyHint: false, untrustedContentHint: false },
          execute: () => {
            setState((current) => ({
              ...current,
              understood: uniqueAdd(current.understood, segment.id),
            }));
            return { paperId: paper.id, segmentId: segment.id, understood: true };
          },
        },
        { signal: controller.signal },
      ),
    ];
    registrations.forEach((registration) => void Promise.resolve(registration).catch(report));
    return () => controller.abort();
  }, [goTo, paper.id, readingPaper.segments, segment, setState]);

  const speak = useCallback((text: string, language: string) => {
    if (!("speechSynthesis" in window)) {
      setNotice("這個瀏覽器不支援朗讀。");
      return;
    }
    window.speechSynthesis.cancel();
    if (speaking) {
      setSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  }, [speaking]);

  function exportJson() {
    downloadText(
      `${fileSafeName(paper.title)}-閱讀進度.json`,
      JSON.stringify(state, null, 2),
      "application/json;charset=utf-8",
    );
    setNotice("已匯出 JSON 閱讀備份。");
  }

  function exportMarkdown() {
    downloadText(`${fileSafeName(paper.title)}-研究筆記.md`, notesAsMarkdown(paper, state), "text/markdown;charset=utf-8");
    setNotice("已匯出 Markdown 筆記。");
  }

  async function importProgress(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as ReaderPaperState;
      if (parsed.version !== 1 || parsed.paperId !== paper.id) {
        throw new Error("這份備份不屬於目前論文。");
      }
      if (parsed.sourceSha256 !== paper.sourceSha256) {
        throw new Error("備份對應的 PDF 版本與目前檔案不同。");
      }
      const validIds = new Set(paper.segments.map((entry) => entry.id));
      const includedIds = new Set(readingPaper.segments.map((entry) => entry.id));
      const previous = paper.segments.find((entry) => entry.id === parsed.currentSegmentId);
      const resume = resolveReadingSegment(paper, previous?.id) ?? readingPaper.segments[0];
      setRawState({
        ...emptyReaderState(paper),
        ...parsed,
        currentSegmentId: resume?.id ?? null,
        seen: resume ? uniqueAdd(parsed.seen.filter((id) => includedIds.has(id)), resume.id) : [],
        understood: parsed.understood.filter((id) => validIds.has(id)),
        bookmarks: parsed.bookmarks.filter((id) => validIds.has(id)),
        notes: Object.fromEntries(Object.entries(parsed.notes).filter(([id]) => validIds.has(id))),
      });
      setNotice("閱讀進度與筆記已匯入。");
    } catch (cause) {
      setNotice(cause instanceof Error ? cause.message : "無法匯入這份備份。");
    }
  }

  async function importCompanion(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      if (file.size > 1024*1024) throw new Error("伴讀備份超過 1 MB，請確認選取正確檔案。");
      setCompanionState(validateCompanionState(JSON.parse(await file.text()), paper));
      setOpenedCompanion(null);
      setNotice("伴讀關聯修正、停靠位置與縮放設定已匯入；正文筆記未變更。");
    } catch (error) { setNotice(error instanceof Error ? error.message : "伴讀備份匯入失敗。"); }
  }

  if (!segment || !hydrated) return <LoadingScreen label="正在恢復上次的閱讀位置……" />;

  const panel = (
    <TranslationPanel
      paper={paper.exhibitCompanion ? paper : readingPaper}
      segment={segment}
      state={state}
      setState={setState}
      speaking={speaking}
      onSpeak={speak}
      onOpenExhibit={paper.inlineExhibitsEnabled ? openExhibit : undefined}
      companion={paper.exhibitCompanion ? { selected: selectedCompanion, ...companionLinks, collapsed: !companionVisible,
        onCorrect: correctCompanion } : undefined}
      onNavigateToSegment={(segmentId, restoreReference) => {
        const index = readingPaper.segments.findIndex((entry) => entry.id === segmentId);
        if (index < 0) return;
        if (restoreReference) {
          setReferenceHistory((current) => [...current, { segmentId: segment.id, restoreReference }]);
        }
        goTo(index);
      }}
    />
  );
  const relatedExhibits = (segment.exhibitIds ?? [])
    .map((id) => readingPaper.exhibits?.find((exhibit) => exhibit.id === id))
    .filter((exhibit): exhibit is PaperExhibit => Boolean(exhibit));
  const focusFragments = relatedExhibits.length && !(paper.inlineExhibitsEnabled && segment.kind === "body")
    ? relatedExhibits.map((exhibit) => ({
        page: exhibit.page,
        bbox: exhibit.bbox,
        pageSize: exhibit.pageSize,
      }))
    : segment.fragments;
  const viewer = (
    <PdfFocusViewer
      pdfUrl={paper.pdfUrl}
      fragments={focusFragments}
      dimOpacity={state.dimOpacity}
      reducedMotion={state.reducedMotion}
      exhibitMentions={paper.inlineExhibitsEnabled ? segment.exhibitMentions : undefined}
      onOpenExhibit={paper.inlineExhibitsEnabled ? openExhibit : undefined}
    />
  );

  return (
    <main className={state.highContrast ? "reader-shell high-contrast" : "reader-shell"}>
      {activeExhibitId && paper.exhibits?.find(exhibit => exhibit.id === activeExhibitId) && (
        <ExhibitPreview key={activeExhibitId} exhibit={paper.exhibits.find(exhibit => exhibit.id === activeExhibitId)!} onClose={() => setActiveExhibitId(null)} />
      )}
      <header className="reader-header">
        <Button type="button" variant="ghost" size="icon" onClick={onBack} aria-label="回到論文書庫">
          <Library />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">{paper.title}</p>
          <div className="mt-1 flex items-center gap-3">
            <Progress value={progress} className="h-1.5 max-w-48 bg-slate-200 [&_[data-slot=progress-indicator]]:bg-amber-600" />
            <span className="shrink-0 text-xs tabular-nums text-slate-500">
              {currentIndex + 1} / {readingPaper.segments.length}
            </span>
          </div>
        </div>

        <Button size="sm" variant="outline" onClick={onGuide} aria-label="切換至本篇互動導讀"><BookOpenText /><span className="hidden sm:inline">互動導讀</span></Button>
        {!!paper.readingQuality?.appendices.length && <Sheet>
          <SheetTrigger asChild><Button size="sm" variant="outline" aria-label="查看完整附錄"><FileText /><span className="hidden sm:inline">完整附錄</span></Button></SheetTrigger>
          <SheetContent className="w-[min(94vw,1100px)] sm:max-w-[1100px]">
            <SheetHeader><SheetTitle>完整附錄</SheetTitle><SheetDescription>補充查核與量測資料；查看內容不改變正文閱讀進度。</SheetDescription></SheetHeader>
            <PaperSupplements paper={paper} state={state} onState={setState} />
          </SheetContent>
        </Sheet>}
        {paper.exhibitCompanion && <Sheet>
          <SheetTrigger asChild><Button size="sm" variant="outline" aria-label="查看本篇全部圖表"><ImageIcon /><span className="hidden sm:inline">全部圖表</span></Button></SheetTrigger>
          <SheetContent className="w-[min(94vw,480px)] sm:max-w-[480px]">
            <SheetHeader><SheetTitle>本篇全部圖表</SheetTitle><SheetDescription>完整圖表不占正文閱讀步驟；未配對圖表也保留在此。</SheetDescription></SheetHeader>
            <div className="min-h-0 flex-1 overflow-auto px-4 pb-6">
              {paper.exhibits?.map(e => <article key={e.id} className="my-3 rounded-xl border p-3 text-sm" data-companion-catalog={e.id}>
                <p className="font-semibold">{e.label} · PDF 第 {e.page} 頁</p><p className="mt-1">{e.captionZh || e.caption}</p>
                <p className="mt-1 text-xs text-slate-500">{paper.exhibitCompanion?.links.some(l => l.exhibitId === e.id && l.confidence === "high") ? "有正文關聯" : "尚未配對正文"}</p>
                <SheetClose asChild><Button size="sm" variant="outline" className="mt-2" onClick={() => setOverviewExhibitId(e.id)}>查看完整圖表</Button></SheetClose>
                <ExhibitArchiveNotes paper={paper} exhibit={e} state={state} onState={setState} />
              </article>)}
            </div>
          </SheetContent>
        </Sheet>}

        <Sheet>
          <SheetTrigger asChild>
            <Button type="button" variant="outline" size="sm" className="size-9 px-0 sm:w-auto sm:px-3" aria-label="開啟段落清單">
              <ListTree /><span className="hidden sm:inline">段落總覽</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-[min(92vw,440px)] sm:max-w-[440px]">
            <SheetHeader className="border-b">
              <SheetTitle>段落總覽</SheetTitle>
              <SheetDescription>直接移動到任意段落，不會改變原始順序。</SheetDescription>
            </SheetHeader>
            <nav className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-3 pb-6">
              {readingPaper.segments.map((entry, index) => (
                <button
                  type="button"
                  key={entry.id}
                  onClick={() => goTo(index)}
                  aria-current={index === currentIndex ? "step" : undefined}
                  className={`my-1 flex w-full gap-3 rounded-xl px-3 py-3 text-left transition hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 ${index === currentIndex ? "bg-amber-50 text-amber-950" : "text-slate-700"}`}
                >
                  <span className="mt-0.5 w-9 shrink-0 text-xs tabular-nums text-slate-400">{String(index + 1).padStart(3, "0")}</span>
                  <span className="line-clamp-3 text-sm leading-5">{entry.paragraphAssessment?.status === "fragment" && <span className="mr-2 text-xs font-semibold text-amber-800">片段 · 待重建</span>}{entry.sourceText}</span>
                </button>
              ))}
            </nav>
          </SheetContent>
        </Sheet>

        <Sheet>
          <SheetTrigger asChild>
            <Button type="button" variant="ghost" size="icon" aria-label="閱讀設定">
              <Settings2 />
            </Button>
          </SheetTrigger>
          <SheetContent className="w-[min(92vw,400px)] sm:max-w-[400px]">
            <SheetHeader className="border-b">
              <SheetTitle>閱讀設定與備份</SheetTitle>
              <SheetDescription>設定僅保存在這台裝置。</SheetDescription>
            </SheetHeader>
            <div className="min-h-0 flex-1 space-y-7 overflow-y-auto px-5 py-3 pb-6">
              <div>
                <div className="flex justify-between text-sm font-medium">
                  <label htmlFor="dim-slider">其他區域暗化</label>
                  <span>{Math.round(state.dimOpacity * 100)}%</span>
                </div>
                <Slider
                  id="dim-slider"
                  className="mt-4"
                  min={30}
                  max={90}
                  step={5}
                  value={[Math.round(state.dimOpacity * 100)]}
                  onValueChange={(value) => setState((current) => ({ ...current, dimOpacity: value[0] / 100 }))}
                />
              </div>
              <label className="flex items-center justify-between gap-4 text-sm font-medium">
                <span>減少動畫</span>
                <Switch checked={state.reducedMotion} onCheckedChange={(checked) => setState((current) => ({ ...current, reducedMotion: checked }))} />
              </label>
              <label className="flex items-center justify-between gap-4 text-sm font-medium">
                <span>高對比模式</span>
                <Switch checked={state.highContrast} onCheckedChange={(checked) => setState((current) => ({ ...current, highContrast: checked }))} />
              </label>
              <div className="border-t pt-6">
                <p className="text-sm font-semibold">閱讀資料備份</p>
                <div className="mt-3 grid gap-2">
                  <Button type="button" variant="outline" onClick={exportJson}><FileDown />匯出 JSON 備份</Button>
                  <Button type="button" variant="outline" onClick={exportMarkdown}><FileText />匯出 Markdown 筆記</Button>
                  <Button type="button" variant="outline" onClick={() => importInputRef.current?.click()}><Upload />匯入 JSON 備份</Button>
                  <input ref={importInputRef} type="file" accept="application/json,.json" className="sr-only" onChange={importProgress} />
                  {paper.exhibitCompanion && <>
                    <Button variant="outline" onClick={() => { downloadText(`${paper.id}-伴讀修正.json`, JSON.stringify(companionState, null, 2), "application/json;charset=utf-8"); setNotice("已匯出伴讀修正備份，不包含研究筆記。"); }}>匯出伴讀修正</Button>
                    <Button variant="outline" onClick={() => importCompanionRef.current?.click()}>匯入伴讀修正</Button>
                    <input ref={importCompanionRef} type="file" accept="application/json,.json" className="sr-only" aria-label="匯入伴讀修正檔案" onChange={importCompanion} />
                  </>}
                </div>
              </div>
            </div>
          </SheetContent>
        </Sheet>
      </header>

      <Tabs value={mobilePane} onValueChange={(value) => setMobilePane(value as MobilePane)} className="shrink-0 gap-0 lg:hidden">
        <TabsList className="mx-auto my-2 grid w-[calc(100%-1rem)] grid-cols-2">
          <TabsTrigger value="source">原始 PDF</TabsTrigger>
          <TabsTrigger value="translation">中文翻譯</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className={`min-h-0 flex-1 ${paper.exhibitCompanion ? "companion-workspace" : "lg:grid lg:grid-cols-[minmax(0,58fr)_minmax(420px,42fr)]"}`}
        data-companion-active={companionVisible ? companionState.layout.dock : "none"}
        data-mobile-pane={mobilePane}
        style={paper.exhibitCompanion ? { "--exhibit-width": `${companionState.layout.width}px`, "--exhibit-height": `${companionState.layout.height}px`, "--mobile-exhibit-height": `${companionState.layout.mobileHeight}px` } as CSSProperties : undefined}>
        <div data-reader-pane="source" className={`${mobilePane === "source" ? "flex" : "hidden"} relative h-full min-h-0 min-w-0 overflow-hidden lg:flex`}>
          {paper.exhibitCompanion && <div className="companion-drop-zone" data-companion-drop="source">拖到此處，停靠原文旁</div>}
          {viewer}
        </div>
        <div data-reader-pane="translation" className={`${mobilePane === "translation" ? "flex" : "hidden"} relative h-full min-h-0 min-w-0 overflow-hidden lg:flex`}>
          {paper.exhibitCompanion && <div className="companion-drop-zone" data-companion-drop="translation">拖到此處，停靠翻譯旁</div>}
          {panel}
        </div>
        {companionVisible && selectedCompanion && <ExhibitCompanionWindow exhibit={selectedCompanion} exhibits={companionExhibits}
          paper={paper} segment={segment} link={companionLinks.accepted.find(l => l.exhibitId === selectedCompanion.id)} hidden={Boolean(overviewExhibitId)}
          state={companionState} onState={setCompanionState} onSelect={openExhibit} onClose={() => setCollapsedCompanion(segment.id)} />}
      </div>

      {overviewExhibitId && paper.exhibits?.find(e => e.id === overviewExhibitId) && <ExhibitOverviewWindow
        paper={paper} exhibit={paper.exhibits.find(e => e.id === overviewExhibitId)!} companionState={companionState}
        state={overviewState} onState={setOverviewState} onClose={() => {
          setOverviewExhibitId(null);
          window.requestAnimationFrame(() => document.querySelector<HTMLButtonElement>('button[aria-label="查看本篇全部圖表"]')?.focus({ preventScroll: true }));
        }} />}

      <footer className="reader-footer">
        <Button type="button" variant="outline" onClick={() => goTo(currentIndex - 1)} disabled={currentIndex === 0}>
          <ArrowLeft />上一段
        </Button>
        {referenceHistory.length > 0 && (
          <Button type="button" variant="outline" size="sm" aria-label="返回上一個位置" onClick={() => {
            const previous = referenceHistory[referenceHistory.length - 1];
            const index = readingPaper.segments.findIndex((entry) => entry.id === previous.segmentId);
            setReferenceHistory((current) => current.slice(0, -1));
            if (index < 0) return;
            goTo(index);
            previous.restoreReference();
          }}>
            <ArrowLeft /><span className="hidden min-[361px]:inline">返回上一個位置</span><span className="min-[361px]:hidden">返回</span>
          </Button>
        )}
        <div className={referenceHistory.length ? "hidden text-center lg:block" : "hidden text-center sm:block"}>
          <p className="max-w-[42vw] truncate text-xs font-semibold text-slate-700">{segment.section}</p>
          <p className="mt-0.5 text-[11px] text-slate-400">方向鍵可切換段落</p>
        </div>
        <Button type="button" onClick={() => goTo(currentIndex + 1)} disabled={currentIndex === readingPaper.segments.length - 1}>
          下一段<ArrowRight />
        </Button>
      </footer>
      <output aria-live="polite" className="pointer-events-none fixed bottom-20 left-1/2 z-[70] -translate-x-1/2 rounded-full bg-slate-950 px-4 py-2 text-sm text-white shadow-xl empty:hidden">
        {notice}
      </output>
    </main>
  );
}

export function ReaderApp() {
  const [manifest, setManifest] = useState<PaperManifest | null>(null);
  const [paper, setPaper] = useState<PaperDocument | null>(null);
  const [guide, setGuide] = useState<PaperSummary | null>(null);
  const [screen, setScreen] = useState<Screen>("library");
  const [loadingPaper, setLoadingPaper] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const routeHash = useRef<string | null>(null);
  const requestNumber = useRef(0);
  const writeRoute = useCallback((hash: string) => {
    routeHash.current = hash ? `#${hash}` : "";
    window.location.hash = hash;
  }, []);
  const returnToLibrary = useCallback(() => {
    requestNumber.current += 1;
    window.speechSynthesis?.cancel();
    writeRoute("");
    setScreen("library");
    setPaper(null);
    setGuide(null);
    setLoadingPaper(false);
  }, [writeRoute]);

  useEffect(() => {
    const controller = new AbortController();
    fetch(publicAssetUrl("/data/manifest.json"), { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`書庫清單回應 ${response.status}。`);
        return response.json() as Promise<PaperManifest>;
      })
      .then((value) => {
        if (!Array.isArray(value.papers) || value.paperCount !== value.papers.length) {
          throw new Error("書庫清單格式不完整。");
        }
        setManifest(value);
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setError(cause instanceof Error ? cause.message : "書庫載入失敗。");
      });
    return () => controller.abort();
  }, [reloadKey]);

  const loadPaper = useCallback(async (summary: PaperSummary, target: "reader" | "editor") => {
    const request = ++requestNumber.current;
    setLoadingPaper(true);
    setError(null);
    try {
      const response = await fetch(publicAssetUrl(summary.dataUrl));
      if (!response.ok) throw new Error(`論文資料回應 ${response.status}。`);
      const document = (await response.json()) as PaperDocument;
      if (document.id !== summary.id || !Array.isArray(document.segments) || !document.segments.length) {
        throw new Error("論文資料與書庫清單不一致。");
      }
      if (request !== requestNumber.current) return;
      setPaper(target === "reader" ? loadCuratorDraft(document) : document);
      setScreen(target);
      writeRoute(target === "reader" ? document.id : `edit:${document.id}`);
    } catch (cause) {
      if (request === requestNumber.current) setError(cause instanceof Error ? cause.message : "論文載入失敗。");
    } finally {
      if (request === requestNumber.current) setLoadingPaper(false);
    }
  }, [writeRoute]);

  const openPaper = useCallback((summary: PaperSummary) => loadPaper(summary, "reader"), [loadPaper]);
  const editPaper = useCallback((summary: PaperSummary) => loadPaper(summary, "editor"), [loadPaper]);

  const openGuide = useCallback((summary: PaperSummary) => {
    requestNumber.current += 1;
    window.speechSynthesis?.cancel();
    setLoadingPaper(false);
    setError(null);
    setGuide(summary);
    setPaper(null);
    setScreen("guide");
    writeRoute(`guide:${summary.id}`);
  }, [writeRoute]);

  useEffect(() => {
    if (!manifest || paper || screen !== "library" || !window.location.hash) return;
    const rawHash = window.location.hash.slice(1);
    const editing = rawHash.startsWith("edit:");
    const guided = rawHash.startsWith("guide:");
    const id = editing ? rawHash.slice(5) : guided ? rawHash.slice(6) : rawHash;
    const summary = manifest.papers.find((entry) => entry.id === id);
    if (!summary) return;
    const timer = window.setTimeout(() => {
      if (guided) openGuide(summary);
      else void loadPaper(summary, editing ? "editor" : "reader");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadPaper, openGuide, manifest, paper, screen]);

  useEffect(() => {
    if (!manifest) return;
    const followRoute = () => {
      if (window.location.hash === routeHash.current) return;
      routeHash.current = window.location.hash;
      const raw = window.location.hash.slice(1);
      if (!raw) { returnToLibrary(); return; }
      const editing = raw.startsWith("edit:");
      const guided = raw.startsWith("guide:");
      const id = editing ? raw.slice(5) : guided ? raw.slice(6) : raw;
      const summary = manifest.papers.find(entry => entry.id === id);
      if (!summary) { returnToLibrary(); return; }
      if (guided) openGuide(summary);
      else void loadPaper(summary, editing ? "editor" : "reader");
    };
    window.addEventListener("hashchange", followRoute);
    return () => window.removeEventListener("hashchange", followRoute);
  }, [manifest, loadPaper, openGuide, returnToLibrary]);

  if (error) return <ErrorScreen message={error} retry={() => {
    setError(null);
    setManifest(null);
    setReloadKey((value) => value + 1);
  }} />;
  if (!manifest || loadingPaper) return <LoadingScreen label={loadingPaper ? "正在開啟論文……" : "正在整理論文書庫……"} />;
  if (screen === "reader" && paper) {
    return (
      <ReaderScreen
        paper={paper}
        onGuide={() => {
          const summary = manifest.papers.find(entry => entry.id === paper.id);
          if (summary) openGuide(summary);
        }}
        onBack={returnToLibrary}
      />
    );
  }
  if (screen === "editor" && paper) {
    return (
      <CuratorScreen
        sourcePaper={paper}
        onBack={returnToLibrary}
        onPreview={(draft) => {
          setPaper(draft);
          setScreen("reader");
          writeRoute(draft.id);
        }}
      />
    );
  }
  if (screen === "guide" && guide) {
    return <GuideScreen paper={guide} manifest={manifest} onSelect={openGuide} onRead={() => void openPaper(guide)} onBack={returnToLibrary} />;
  }
  return <LibraryScreen manifest={manifest} onOpen={openPaper} onEdit={editPaper} onGuide={openGuide} />;
}
