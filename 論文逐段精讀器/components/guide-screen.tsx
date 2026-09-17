"use client";

import { publicAssetUrl } from "@/lib/public-asset-url";
import { useState } from "react";
import { ArrowLeft, ArrowRight, BookOpenText, Library } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { PaperManifest, PaperSummary } from "@/lib/paper-types";
import versionAudit from "@/content/guide-version-audit.json";

export function GuideScreen({ paper, manifest, onSelect, onRead, onBack }: {
  paper: PaperSummary;
  manifest: PaperManifest;
  onSelect: (paper: PaperSummary) => void;
  onRead: () => void;
  onBack: () => void;
}) {
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const version = versionAudit.papers.find(entry => entry.id === paper.id)?.sha256 ?? "local";
  const frameKey = `${paper.id}:${version}`;
  const index = manifest.papers.findIndex(entry => entry.id === paper.id);
  return <main className="flex h-dvh min-h-0 flex-col bg-[#f3f1eb]" data-guide-screen={paper.id}>
    <header className="flex shrink-0 flex-wrap items-center gap-2 border-b bg-[#f8f7f2] px-3 py-3 sm:px-5">
      <Button variant="ghost" size="icon" aria-label="回到論文書庫" onClick={onBack}><Library /></Button>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-amber-700">互動導讀 · {String(paper.number).padStart(2, "0")}</p>
        <h1 className="truncate text-sm font-semibold">{paper.title}</h1>
      </div>
      <Button onClick={onRead} aria-label="切換至本篇逐段精讀"><BookOpenText /><span>逐段精讀</span></Button>
      <nav className="flex w-full items-center gap-2 sm:w-auto" aria-label="切換導讀論文">
        <select className="h-9 min-w-0 flex-1 rounded-md border bg-white px-2 text-sm sm:max-w-64" value={paper.id} aria-label="選擇導讀論文" onChange={event => {
          const next = manifest.papers.find(entry => entry.id === event.target.value);
          if (next) onSelect(next);
        }}>
          {manifest.papers.map(entry => <option key={entry.id} value={entry.id}>{String(entry.number).padStart(2, "0")}｜{entry.title}</option>)}
        </select>
        <Button variant="outline" size="icon" aria-label="上一篇導讀" disabled={index <= 0} onClick={() => onSelect(manifest.papers[index - 1])}><ArrowLeft /></Button>
        <Button variant="outline" size="icon" aria-label="下一篇導讀" disabled={index >= manifest.papers.length - 1} onClick={() => onSelect(manifest.papers[index + 1])}><ArrowRight /></Button>
      </nav>
    </header>
    <section className="relative min-h-0 flex-1" aria-label="完整互動導讀">
      {loadedId !== frameKey && <p className="pointer-events-none absolute left-1/2 top-4 z-10 -translate-x-1/2 rounded-lg border bg-white px-4 py-2 text-sm shadow" role="status">正在開啟導讀……</p>}
      <iframe key={frameKey} src={publicAssetUrl(`/guides/${paper.id}.html?v=${version}`)} title={`${paper.title}：互動導讀`} className="h-full w-full border-0 bg-white" sandbox="allow-scripts allow-same-origin allow-modals allow-popups" onLoad={() => setLoadedId(frameKey)} />
    </section>
  </main>;
}
