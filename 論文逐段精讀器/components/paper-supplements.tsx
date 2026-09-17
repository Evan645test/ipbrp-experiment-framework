"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ExhibitArchiveNotes, ExhibitImage } from "@/components/exhibit-companion";
import type { PaperDocument, PaperSegment, ReaderPaperState } from "@/lib/paper-types";

type StateUpdater = (update: (current: ReaderPaperState) => ReaderPaperState) => void;

function PassageNotes({ segment, state, onState }: { segment: PaperSegment; state: ReaderPaperState; onState: StateUpdater }) {
  return <div className="mt-3">
    <Button size="sm" variant="outline" onClick={() => onState(c => ({ ...c, bookmarks: c.bookmarks.includes(segment.id) ? c.bookmarks.filter(id => id !== segment.id) : [...c.bookmarks, segment.id] }))}>
      {state.bookmarks.includes(segment.id) ? "移除書籤" : "加入書籤"}
    </Button>
    <label className="mt-3 block text-sm">研究筆記<Textarea className="mt-1 min-h-20" aria-label={`${segment.section}的研究筆記`} value={state.notes[segment.id] ?? ""}
      onChange={e => onState(c => ({ ...c, notes: { ...c.notes, [segment.id]: e.target.value } }))} /></label>
  </div>;
}

export function ArchivedPassageNotes({ paper, segment, state, onState }: { paper: PaperDocument; segment: PaperSegment; state: ReaderPaperState; onState: StateUpdater }) {
  const archived = paper.segments.filter(s => s.mergedIntoSegmentId === segment.id && s.kind !== "heading");
  if (!archived.length) return null;
  return <details className="mt-5 rounded-xl border bg-white p-4" data-merged-passage-notes>
    <summary className="cursor-pointer text-sm font-medium">合併前的段落筆記與書籤（{archived.length}）</summary>
    {archived.map(s => <div key={s.id} className="mt-3 border-t pt-3"><p className="text-xs text-slate-500">舊段落 {s.id} · PDF 第 {[...new Set(s.fragments.map(f => f.page))].join("、")} 頁</p>
      <PassageNotes segment={s} state={state} onState={onState} /></div>)}
  </details>;
}

export function PaperSupplements({ paper, state, onState }: { paper: PaperDocument; state: ReaderPaperState; onState: StateUpdater }) {
  const [appendixId, setAppendixId] = useState(paper.readingQuality?.appendices[0]?.exhibit.id);
  const [zooms, setZooms] = useState<Record<string, number>>({});
  const appendix = paper.readingQuality?.appendices.find(a => a.exhibit.id === appendixId);
  return <div className="flex min-h-0 flex-1 flex-col" data-paper-supplements>
    <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-6">
        {!paper.readingQuality?.appendices.length && <p className="py-4 text-sm leading-7 text-slate-600">這份原始 PDF 沒有可獨立呈現的完整附錄。正文提到的另附補充資料，仍請依作者提供的取得方式查閱。</p>}
        <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="切換完整附錄">
          {paper.readingQuality?.appendices.map(a => <Button key={a.exhibit.id} size="sm" variant={a.exhibit.id === appendixId ? "default" : "outline"} aria-pressed={a.exhibit.id === appendixId}
            data-appendix-tab={a.exhibit.id} onClick={() => setAppendixId(a.exhibit.id)}>{a.exhibit.captionZh}</Button>)}
        </div>
        {appendix && <article className="grid min-w-0 gap-4 md:grid-cols-2" data-complete-appendix={appendix.exhibit.id}>
          <div className="flex h-[min(55dvh,560px)] min-h-64 min-w-0 flex-col overflow-hidden rounded-xl border bg-white">
            <ExhibitImage key={appendix.exhibit.id} exhibit={appendix.exhibit} mode="附錄" zoom={zooms[appendix.exhibit.id] ?? 1}
              onZoom={zoom => setZooms(c => ({ ...c, [appendix.exhibit.id]: zoom }))} />
          </div>
          <div className="min-w-0 rounded-xl border bg-white p-4 text-sm leading-7">
            <h3 className="font-semibold">完整附錄 · PDF 第 {appendix.exhibit.page} 頁</h3>
            <p className="text-xs text-slate-500">中文翻譯與讀圖說明為 AI 草稿，完整原圖保留作者原始內容。</p>
            <p className="mt-3 whitespace-pre-line" data-appendix-translation>{appendix.faithfulZh}</p>
            <h4 className="mt-4 font-semibold">如何搭配正文閱讀</h4>
            {appendix.guideZh.map(text => <p className="mt-2" key={text}>{text}</p>)}
            {appendix.relatedSegmentIds.map(id => {
              const s = paper.segments.find(s => s.id === id && !s.excluded);
              return s && <details key={id} className="mt-3 rounded-lg border p-3"><summary className="cursor-pointer">正文相關說明 · {s.section} · PDF 第 {[...new Set(s.fragments.map(f => f.page))].join("、")} 頁</summary>
                <p className="mt-2 whitespace-pre-line">{s.translation.faithfulZh}</p><details className="mt-2"><summary className="cursor-pointer">展開英文原文</summary><p className="mt-2 font-serif text-slate-600" lang="en">{s.sourceText}</p></details>
              </details>;
            })}
            <ExhibitArchiveNotes paper={paper} exhibit={appendix.exhibit} state={state} onState={onState} />
          </div>
        </article>}
    </div>
  </div>;
}
