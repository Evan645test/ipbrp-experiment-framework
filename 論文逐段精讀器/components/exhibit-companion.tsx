"use client";

import { publicAssetUrl } from "@/lib/public-asset-url";
import NextImage from "next/image";
import { useEffect, useMemo, useRef, useState, type PointerEvent, type KeyboardEvent } from "react";
import { GripHorizontal, Maximize2, Minus, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ExhibitCompanionLink, PaperDocument, PaperExhibit, PaperSegment, ReaderPaperState } from "@/lib/paper-types";
import type { CompanionState, ExhibitDock } from "@/lib/companion-state";
import { exhibitOverviewPassages } from "@/lib/companion-state";

function bounds(layout: CompanionState["layout"]) {
  const width = Math.min(layout.width, window.innerWidth - 24);
  const height = Math.min(layout.height, window.innerHeight - 100);
  return { ...layout, x: Math.max(12, Math.min(layout.x, window.innerWidth-width-12)),
    y: Math.max(12, Math.min(layout.y, window.innerHeight-height-12)) };
}

export function ExhibitImage({ exhibit, zoom, onZoom, mode = "伴讀" }: { exhibit: PaperExhibit; zoom: number; onZoom: (value: number) => void; mode?: "伴讀" | "總覽" | "附錄" }) {
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const scroller = useRef<HTMLDivElement>(null);
  const pan = useRef<{ id: number; x: number; y: number; left: number; top: number } | null>(null);
  function change(value: number) {
    onZoom(Math.min(4, Math.max(0.5, value)));
    if (value === 1) scroller.current?.scrollTo({ left: 0, top: 0 });
  }
  return <>
    <div className="flex shrink-0 flex-wrap items-center gap-1 border-b bg-white px-3 py-2">
      <Button size="icon-sm" variant="outline" aria-label={`縮小${mode}圖表`} disabled={zoom <= 0.5} onClick={() => change(zoom-0.25)}><Minus /></Button>
      <output className="w-12 text-center text-xs" aria-label={`${mode}圖表縮放比例`}>{Math.round(zoom*100)}%</output>
      <Button size="icon-sm" variant="outline" aria-label={`放大${mode}圖表`} disabled={zoom >= 4} onClick={() => change(zoom+0.25)}><Plus /></Button>
      <Button size="sm" variant="ghost" onClick={() => change(1)}><Maximize2 />適合視窗</Button>
      <Button size="sm" variant="ghost" onClick={() => { change(1); }}>重設圖片</Button>
    </div>
    <div ref={scroller} className={`min-h-0 flex-1 overflow-auto overscroll-contain bg-white ${zoom > 1 ? "cursor-grab" : ""}`} tabIndex={0}
      aria-label={`${exhibit.label} 完整原圖，放大後可拖曳或捲動查看`} data-companion-image-scroll
      onPointerDown={event => {
        if (zoom <= 1 || event.pointerType !== "mouse" || event.button !== 0) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        pan.current = { id: event.pointerId, x: event.clientX, y: event.clientY, left: event.currentTarget.scrollLeft, top: event.currentTarget.scrollTop };
        event.preventDefault();
      }} onPointerMove={event => {
        const start = pan.current;
        if (!start || start.id !== event.pointerId) return;
        event.currentTarget.scrollLeft = start.left-event.clientX+start.x;
        event.currentTarget.scrollTop = start.top-event.clientY+start.y;
      }} onPointerUp={event => {
        pan.current = null;
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      }} onPointerCancel={() => { pan.current = null; }} onLostPointerCapture={() => { pan.current = null; }}>
      {failed ? <div role="alert" className="p-4 text-sm text-red-800">原圖載入失敗，正文與閱讀位置未改動。
        <Button variant="outline" size="sm" onClick={() => { setFailed(false); setRetry(v => v+1); }}>重試</Button></div> :
        <NextImage src={publicAssetUrl(exhibit.imageUrl)+(retry ? `?retry=${retry}` : "")} alt={exhibit.captionZh || exhibit.caption}
          width={Math.round((exhibit.bbox[2]-exhibit.bbox[0])*300/72)} height={Math.round((exhibit.bbox[3]-exhibit.bbox[1])*300/72)}
          unoptimized draggable={false} className="h-auto max-w-none select-none" style={{ width: `${zoom*100}%` }} onError={() => setFailed(true)} />}
    </div>
  </>;
}

export function ExhibitCompanionWindow({ paper, segment, link, hidden = false, exhibit, exhibits, state, onState, onSelect, onClose }: {
  paper: PaperDocument; segment: PaperSegment; link?: ExhibitCompanionLink; hidden?: boolean;
  exhibit: PaperExhibit; exhibits: PaperExhibit[]; state: CompanionState;
  onState: (update: (current: CompanionState) => CompanionState) => void;
  onSelect: (id: string) => void; onClose: () => void;
}) {
  const layout = state.layout;
  const ref = useRef<HTMLElement>(null);
  const [dragging, setDragging] = useState(false);
  const gesture = useRef<{ id: number; x: number; y: number; origin: CompanionState["layout"]; resize: boolean } | null>(null);
  function place(dock: ExhibitDock) {
    const rect = ref.current?.getBoundingClientRect();
    onState(current => ({ ...current, layout: bounds({ ...current.layout, dock,
      ...(dock === "floating" && rect ? { x: rect.x, y: rect.y } : {}) }) }));
  }
  function start(event: PointerEvent<HTMLElement>, resize: boolean) {
    if (!event.isPrimary || event.button !== 0) return;
    const rect = ref.current?.getBoundingClientRect();
    const origin = { ...layout, ...(!resize && rect ? { dock: "floating" as const, x: rect.x, y: rect.y } : {}) };
    gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY, origin, resize };
    event.currentTarget.setPointerCapture(event.pointerId);
    if (!resize) { onState(c => ({ ...c, layout: bounds(origin) })); setDragging(true); }
    event.preventDefault();
  }
  function move(event: PointerEvent<HTMLElement>) {
    const start = gesture.current;
    if (!start || start.id !== event.pointerId) return;
    const dx = event.clientX-start.x, dy = event.clientY-start.y;
    const next = start.resize ? { ...start.origin,
      width: Math.max(280, Math.min(1600, start.origin.width+dx)),
      height: Math.max(180, Math.min(1400, start.origin.height+dy)),
      mobileHeight: Math.max(140, Math.min(800, start.origin.mobileHeight+dy)) }
      : { ...start.origin, x: start.origin.x+dx, y: start.origin.y+dy };
    onState(c => ({ ...c, layout: bounds(next) }));
  }
  function end(event: PointerEvent<HTMLElement>) {
    const start = gesture.current;
    if (!start || start.id !== event.pointerId) return;
    if (!start.resize && event.type === "pointerup") {
      const zones = document.querySelectorAll<HTMLElement>("[data-companion-drop]");
      for (const zone of zones) {
        const r = zone.getBoundingClientRect();
        if (r.width && r.height && event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom) {
          place(zone.dataset.companionDrop as ExhibitDock);
          break;
        }
      }
    }
    gesture.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }
  function keyMove(event: KeyboardEvent<HTMLButtonElement>) {
    const directions: Record<string, [number, number]> = { ArrowLeft: [-1,0], ArrowRight: [1,0], ArrowUp: [0,-1], ArrowDown: [0,1] };
    const dir = directions[event.key];
    if (!dir) return;
    event.preventDefault(); event.stopPropagation();
    const rect = ref.current?.getBoundingClientRect();
    const step = event.shiftKey ? 40 : 10;
    onState(c => ({ ...c, layout: bounds({ ...c.layout, dock: "floating", x: (rect?.x ?? c.layout.x)+dir[0]*step, y: (rect?.y ?? c.layout.y)+dir[1]*step }) }));
  }
  return <aside ref={ref} role="region" aria-label="圖表伴讀視窗" data-companion-window={exhibit.id} data-companion-dock={layout.dock}
    data-companion-dragging={dragging ? "true" : "false"}
    className={`companion-window ${layout.dock === "floating" ? "companion-floating" : ""}`}
    aria-hidden={hidden || undefined} inert={hidden || undefined}
    style={{ visibility: hidden ? "hidden" : undefined, ...(layout.dock === "floating" ? { left: `clamp(12px, ${layout.x}px, max(12px, 100vw - min(${layout.width}px, 100vw - 24px) - 12px))`,
      top: `clamp(12px, ${layout.y}px, max(12px, 100dvh - min(${layout.height}px, 100dvh - 100px) - 12px))`,
      width: `min(${layout.width}px, calc(100vw - 24px))`, height: `min(${layout.height}px, calc(100dvh - 100px))` } : {}) }}
    onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}>
    <div className="flex shrink-0 items-center border-b bg-amber-50 px-3 py-2">
      <button type="button" className="flex min-w-0 flex-1 touch-none items-center gap-2 text-left text-sm font-semibold cursor-grab"
        aria-label="拖曳伴讀視窗，方向鍵亦可移動" data-companion-drag-handle onKeyDown={keyMove}
        onPointerDown={e => start(e, false)} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end}>
        <GripHorizontal className="size-4 shrink-0" /><span className="truncate">{exhibit.label} · PDF 第 {exhibit.page} 頁</span>
      </button>
      <Button size="icon-sm" variant="ghost" aria-label="收起本段伴讀圖表" onClick={onClose}><X /></Button>
    </div>
    {dragging && <p className="px-3 text-xs text-amber-900">拖到文字區頂端停靠，或放開保留浮動。</p>}
    <div className="flex shrink-0 flex-wrap gap-1 border-b px-2 py-1">
      {(["source", "translation", "floating"] as const).map(dock => <Button key={dock} size="sm" variant={layout.dock === dock ? "secondary" : "ghost"} onClick={() => place(dock)}>
        {dock === "source" ? "原文旁" : dock === "translation" ? "翻譯旁" : "浮動"}</Button>)}
      <Button size="sm" variant="ghost" onClick={() => onState(c => ({ ...c, layout: { ...c.layout, width: 420, height: 380, x: 32, y: 100, mobileHeight: 340 } }))}>重設視窗</Button>
    </div>
    {exhibits.length > 1 && <div className="flex shrink-0 gap-1 overflow-x-auto border-b px-2 py-1" role="group" aria-label="本段相關圖表切換">
      {exhibits.map(e => <Button size="sm" variant={e.id === exhibit.id ? "default" : "outline"} key={e.id} aria-pressed={e.id === exhibit.id} data-companion-tab={e.id} onClick={() => onSelect(e.id)}>{e.kind === "table" ? "表" : "圖"} {e.number}</Button>)}
    </div>}
    <p className="shrink-0 border-b px-3 py-2 text-xs leading-5">{exhibit.captionZh || exhibit.caption}</p>
    <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain" data-companion-content-scroll>
      <div className="companion-picture-block flex min-h-0 flex-col">
        <ExhibitImage key={exhibit.id} exhibit={exhibit} zoom={state.zooms[exhibit.id] ?? 1}
          onZoom={zoom => onState(c => ({ ...c, zooms: { ...c.zooms, [exhibit.id]: zoom } }))} />
      </div>
      <ExhibitStudyPanel paper={paper} segment={segment} exhibit={exhibit} link={link} />
    </div>
    <button type="button" className="flex shrink-0 touch-none items-center justify-end gap-1 border-t bg-slate-50 px-3 py-1 text-[11px] text-slate-600 cursor-nwse-resize"
      aria-label="調整伴讀視窗尺寸，可拖曳或使用方向鍵" data-companion-resize-handle
      onPointerDown={e => start(e, true)} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end}
      onKeyDown={event => {
        const dx = event.key === "ArrowRight" ? 20 : event.key === "ArrowLeft" ? -20 : 0;
        const dy = event.key === "ArrowDown" ? 20 : event.key === "ArrowUp" ? -20 : 0;
        if (!dx && !dy) return;
        event.preventDefault(); event.stopPropagation();
        onState(c => ({ ...c, layout: bounds({ ...c.layout, width: Math.max(280, Math.min(1600, c.layout.width+dx)),
          height: Math.max(180, Math.min(1400, c.layout.height+dy)), mobileHeight: Math.max(140, Math.min(800, c.layout.mobileHeight+dy)) }) }));
      }}><GripHorizontal className="size-3" />拖曳此處調整尺寸</button>
  </aside>;
}

function ExhibitGuide({ paper, exhibit }: { paper: PaperDocument; exhibit: PaperExhibit }) {
  const study = paper.exhibitCompanion?.studies[exhibit.id];
  if (!study) return <p className="text-sm text-slate-600">此圖表尚無可追溯的解讀，不根據圖名補寫。</p>;
  return <div data-exhibit-guide={exhibit.id}>
    <h3 className="font-semibold">圖表怎麼讀</h3><p>{study.summaryZh}</p>
    <details className="mt-2 rounded-lg border bg-white p-3"><summary className="cursor-pointer font-medium">展開欄位／座標軸、符號與解讀限制</summary>
      {study.guideZh.map(text => <p key={text} className="mt-2">{text}</p>)}
      <h4 className="mt-3 font-semibold">解讀限制與原文疑點</h4>
      {study.limitsZh.map(text => <p key={text} className="mt-2">{text}</p>)}
    </details>
  </div>;
}

function AuthorPassage({ segment }: { segment: PaperSegment }) {
  return <div data-author-passage={segment.id}>
    <p className="text-xs text-slate-600">中文翻譯 · {segment.translation.status === "reviewed" ? "已校訂" : "AI 草稿"}</p>
    <p className="mt-2 whitespace-pre-line">{segment.translation.faithfulZh || "尚未有中文翻譯，不補寫作者說明。"}</p>
    <details className="mt-3 rounded-lg border bg-white p-3"><summary className="cursor-pointer font-medium">展開英文原文</summary>
      <p className="mt-2 whitespace-pre-line font-serif text-slate-600" lang="en">{segment.sourceText}</p>
    </details>
  </div>;
}

export function ExhibitStudyPanel({ paper, segment, exhibit, link }: {
  paper: PaperDocument; segment: PaperSegment; exhibit: PaperExhibit; link?: ExhibitCompanionLink;
}) {
  return <section className="border-t border-amber-300 bg-amber-50/60 p-4 text-sm leading-7" data-companion-study={exhibit.id}>
    <p className="text-xs text-amber-900">{exhibit.label} · 來源 PDF 第 {exhibit.page} 頁 · AI 解讀草稿</p>
    <div className="mt-3"><ExhibitGuide paper={paper} exhibit={exhibit} /></div>
    <h3 className="mt-4 font-semibold">本段與圖表的關係 · AI 解釋</h3>
    <p>{link?.relationshipZh ?? "目前是你另行開啟的圖表，尚未與本段建立關聯；不能視為作者在本段的說明。"}</p>
    {link && <div className="mt-4" data-companion-source={segment.id}>
      <h3 className="font-semibold">作者在論文中的說明 · 目前段落</h3>
      <p className="text-xs text-slate-600">{segment.section} · PDF 第 {[...new Set(segment.fragments.map(f => f.page))].join("、")} 頁。語意關聯不代表作者在此明確引用圖號。</p>
      <AuthorPassage segment={segment} />
    </div>}
  </section>;
}

export interface ExhibitOverviewState {
  width: number; height: number; x: number; y: number; mobileHeight: number;
  zooms: Record<string, number>;
}

export function ExhibitOverviewWindow({ paper, exhibit, companionState, state, onState, onClose }: {
  paper: PaperDocument; exhibit: PaperExhibit; companionState: CompanionState; state: ExhibitOverviewState;
  onState: (update: (current: ExhibitOverviewState) => ExhibitOverviewState) => void; onClose: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const gesture = useRef<{ id: number; x: number; y: number; origin: ExhibitOverviewState; mode: "move" | "resize" | "split" } | null>(null);
  const passages = useMemo(() => exhibitOverviewPassages(paper, exhibit.id, companionState), [paper, exhibit.id, companionState]);
  useEffect(() => { closeRef.current?.focus({ preventScroll: true }); }, []);
  function constrain(value: ExhibitOverviewState) {
    const width = Math.min(value.width, window.innerWidth - 24), height = Math.min(value.height, window.innerHeight - 100);
    return { ...value, x: Math.max(12, Math.min(value.x, window.innerWidth-width-12)),
      y: Math.max(12, Math.min(value.y, window.innerHeight-height-12)) };
  }
  function start(event: PointerEvent<HTMLButtonElement>, mode: "move" | "resize" | "split") {
    if (!event.isPrimary || event.button !== 0) return;
    const r = ref.current?.getBoundingClientRect();
    gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY, mode,
      origin: { ...state, ...(r ? { x: r.x, y: r.y, ...(mode === "resize" ? { width: r.width, height: r.height } : {}) } : {}) } };
    event.currentTarget.setPointerCapture(event.pointerId); event.preventDefault();
  }
  function move(event: PointerEvent<HTMLButtonElement>) {
    const g = gesture.current; if (!g || g.id !== event.pointerId) return;
    const dx = event.clientX-g.x, dy = event.clientY-g.y;
    onState(c => constrain({ ...c, ...(g.mode === "move" ? { x: g.origin.x+dx, y: g.origin.y+dy }
      : g.mode === "split" ? { mobileHeight: Math.max(140, Math.min(800, g.origin.mobileHeight+dy)) }
      : { width: Math.max(280, Math.min(1600, g.origin.width+dx)), height: Math.max(280, Math.min(1400, g.origin.height+dy)) }) }));
  }
  function end(event: PointerEvent<HTMLButtonElement>) {
    if (gesture.current?.id !== event.pointerId) return;
    gesture.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }
  function keyboard(event: KeyboardEvent<HTMLButtonElement>, mode: "move" | "resize" | "split") {
    const dx = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    const dy = event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if ((!dx && !dy) || (mode === "split" && !dy)) return;
    event.preventDefault(); event.stopPropagation();
    const step = event.shiftKey ? 40 : 10, r = ref.current?.getBoundingClientRect();
    onState(c => constrain({ ...c, ...(mode === "move" ? { x: (r?.x ?? c.x)+dx*step, y: (r?.y ?? c.y)+dy*step }
      : mode === "split" ? { mobileHeight: Math.max(140, Math.min(800, c.mobileHeight+dy*step)) }
      : { width: Math.max(280, Math.min(1600, (r?.width ?? c.width)+dx*step)), height: Math.max(280, Math.min(1400, (r?.height ?? c.height)+dy*step)) }) }));
  }
  return <aside ref={ref} role="region" aria-label="圖表總覽閱讀視窗" data-exhibit-overview={exhibit.id}
    className="exhibit-overview-window"
    style={{ left: `clamp(12px, ${state.x}px, max(12px, 100vw - min(${state.width}px, 100vw - 24px) - 12px))`,
      top: `clamp(12px, ${state.y}px, max(12px, 100dvh - min(${state.height}px, 100dvh - 100px) - 12px))`,
      width: `min(${state.width}px, calc(100vw - 24px))`, height: `min(${state.height}px, calc(100dvh - 100px))` }}
    onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}>
    <div className="flex shrink-0 items-center gap-2 border-b bg-amber-50 px-3 py-2">
      <button type="button" className="flex min-w-0 flex-1 cursor-grab touch-none items-center gap-2 text-left text-sm font-semibold"
        aria-label="拖曳圖表總覽視窗，方向鍵亦可移動" data-overview-drag-handle
        onPointerDown={e => start(e, "move")} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end}
        onKeyDown={e => keyboard(e, "move")}>
        <GripHorizontal className="size-4 shrink-0" /><span className="truncate">{exhibit.label} · 圖表與各段說明</span>
      </button>
      <Button size="sm" variant="ghost" onClick={() => onState(c => ({ ...c, width: 1100, height: 750, x: 32, y: 90, mobileHeight: 300 }))}>重設視窗</Button>
      <Button ref={closeRef} size="icon-sm" variant="ghost" aria-label="關閉圖表總覽，返回原閱讀畫面" onClick={onClose}><X /></Button>
    </div>
    <div className="exhibit-overview-content" style={{ "--overview-mobile-height": `${state.mobileHeight}px` } as import("react").CSSProperties}>
      <div className="flex min-h-0 min-w-0 flex-col overflow-hidden border-r" data-overview-picture>
        <p className="shrink-0 border-b p-3 text-xs leading-5">{exhibit.captionZh || exhibit.caption} · PDF 第 {exhibit.page} 頁</p>
        <ExhibitImage key={exhibit.id} mode="總覽" exhibit={exhibit} zoom={state.zooms[exhibit.id] ?? 1}
          onZoom={zoom => onState(c => ({ ...c, zooms: { ...c.zooms, [exhibit.id]: zoom } }))} />
      </div>
      <button type="button" className="overview-mobile-divider touch-none border-y bg-slate-50 text-[11px] text-slate-600"
        aria-label="調整總覽上下區域高度，可拖曳或使用上下方向鍵" data-overview-split-handle
        onPointerDown={e => start(e, "split")} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end}
        onKeyDown={e => keyboard(e, "split")}><GripHorizontal className="mx-auto size-4" /></button>
      <div className="min-h-0 min-w-0 overflow-y-auto overscroll-contain bg-amber-50/30 p-4 text-sm leading-7" data-overview-explanations key={exhibit.id}>
        <p className="mb-3 text-xs text-amber-900">圖表解讀與關聯說明為 AI 草稿，與作者原文及翻譯分開呈現。</p>
        <ExhibitGuide paper={paper} exhibit={exhibit} />
        <h3 className="mt-6 font-semibold">各段如何引用、解釋或敘述這張圖表</h3>
        <p className="text-xs text-slate-600">依論文順序排列；展開內容不改變正文閱讀位置或已讀進度。語意／人工關聯不等於作者明確引用。</p>
        {!passages.length && <p className="mt-3 text-slate-600">目前沒有已接受的正文關聯，未確認候選不列入；圖表仍可完整閱讀。</p>}
        {passages.map(({ segment, link, label }) => <details key={segment.id} className="mt-3 rounded-lg border bg-white p-3" data-overview-source={segment.id}>
          <summary className="cursor-pointer font-medium">{segment.section} · PDF 第 {[...new Set(segment.fragments.map(f => f.page))].join("、")} 頁 · {label}</summary>
          <h4 className="mt-3 font-semibold">本段與圖表的關係 · AI 解釋</h4><p>{link.relationshipZh}</p>
          <h4 className="mt-3 font-semibold">作者在論文中的說明</h4><AuthorPassage segment={segment} />
        </details>)}
      </div>
    </div>
    <button type="button" className="flex shrink-0 cursor-nwse-resize touch-none items-center justify-end gap-1 border-t bg-slate-50 px-3 py-1 text-[11px] text-slate-600"
      aria-label="調整圖表總覽視窗尺寸，可拖曳或使用方向鍵" data-overview-resize-handle
      onPointerDown={e => start(e, "resize")} onPointerMove={move} onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end}
      onKeyDown={e => keyboard(e, "resize")}><GripHorizontal className="size-3" />拖曳此處調整尺寸</button>
  </aside>;
}

export function ExhibitArchiveNotes({ paper, exhibit, state, onState }: {
  paper: PaperDocument; exhibit: PaperExhibit; state: ReaderPaperState;
  onState: (update: (current: ReaderPaperState) => ReaderPaperState) => void;
}) {
  const id = exhibit.captionSegmentId;
  if (!id) return null;
  const ids = paper.segments.filter(s => s.id === id || s.mergedIntoSegmentId === id).map(s => s.id);
  return <details className="mt-3 rounded border bg-white p-3 text-sm"><summary className="cursor-pointer">圖表筆記與舊書籤</summary>
    <Button size="sm" variant="outline" className="mt-2" onClick={() => onState(c => ({ ...c, bookmarks: c.bookmarks.includes(id) ? c.bookmarks.filter(x => x !== id) : [...c.bookmarks, id] }))}>{state.bookmarks.includes(id) ? "移除圖表書籤" : "加入圖表書籤"}</Button>
    <label className="mt-2 block">完整圖表筆記<textarea className="mt-1 block min-h-20 w-full rounded border p-2" value={state.notes[id] ?? ""} onChange={e => onState(c => ({ ...c, notes: { ...c.notes, [id]: e.target.value } }))} /></label>
    {ids.filter(x => x !== id && (state.notes[x] || state.bookmarks.includes(x))).map(x => <p className="mt-2 whitespace-pre-line" key={x}>舊片段 {x} {state.bookmarks.includes(x) ? "· 已加書籤" : ""}<br />{state.notes[x]}</p>)}
  </details>;
}
