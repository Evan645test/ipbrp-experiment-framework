"use client";

import { publicAssetUrl } from "@/lib/public-asset-url";
import { useRef, useState } from "react";
import { ArrowLeft, ArrowRight, BookOpenText, ChevronDown, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import type { PaperCitation, PaperDocument, PaperReference, PaperSegment } from "@/lib/paper-types";

function pagesLabel(reference: PaperReference): string {
  return [...new Set(reference.fragments.map((fragment) => fragment.page))].join("、");
}

function abstractSourceLabel(reference: PaperReference): string {
  switch (reference.abstract.sourceType) {
    case "crossref": return "出版社提交的 Crossref 摘要紀錄";
    case "author": return "作者機構官方文獻頁的 Abstract";
    case "openalex": return "OpenAlex 資料庫收錄的摘要（非 AI 研究總結）";
    case "semantic-scholar": return "Semantic Scholar 資料庫的 Abstract 欄位（未使用 TLDR 或 AI 總結）";
    case "europe-pmc": return "Europe PMC 資料庫收錄的原始 Abstract";
    case "openaire": return "OpenAIRE 收錄的來源機構摘要／描述欄位（非本工具生成的總結）";
    case "doaj": return "DOAJ 開放取用期刊資料庫收錄的 Abstract";
    case "ebsco": return "EBSCO 公開紀錄的 Abstract 欄位（編撰者未標明，非本工具生成的總結）";
    case "eric": return reference.abstract.abstractOrigin === "ERIC" ? "ERIC 資料庫編撰的文獻摘要（非作者原始 Abstract）" : reference.abstract.abstractOrigin === "As Provided" ? "ERIC 收錄、由出版社或作者提供的 Abstract" : "ERIC 資料庫收錄的文獻摘要（編撰者未標明）";
    default: return "出版社文獻頁的 Abstract";
  }
}

function safeExternalUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

export function SegmentReferences({
  paper,
  segment,
  onNavigateToSegment,
}: {
  paper: PaperDocument;
  segment: PaperSegment;
  onNavigateToSegment: (segmentId: string, restoreReference?: () => void) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selectedCitationId, setSelectedCitationId] = useState<string | null>(null);
  const [selectedReferenceId, setSelectedReferenceId] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const restoreScrollTopRef = useRef<number | null>(null);
  const citations = (paper.citations ?? []).filter((citation) => citation.segmentId === segment.id && segment.sourceText.includes(citation.sourceContext));
  const citation = paper.citations?.find((entry) => entry.id === selectedCitationId);
  const reference = paper.references?.find((entry) => entry.id === selectedReferenceId);
  const citedSegment = paper.segments.find((entry) => entry.id === citation?.segmentId) ?? segment;
  const sourceUrl = safeExternalUrl(reference?.abstract.sourceUrl ?? null);
  const relatedCitations = reference
    ? (paper.citations ?? []).filter((entry) => entry.referenceIds.includes(reference.id) && entry.matchStatus === "matched")
    : [];
  const relatedSegmentIds = [...new Set(relatedCitations.map((entry) => entry.segmentId))];

  function openCitation(entry: PaperCitation) {
    setExpandedSections({});
    setSelectedCitationId(entry.id);
    setSelectedReferenceId(entry.matchStatus === "matched" ? entry.referenceIds[0] : null);
    setOpen(true);
  }

  function navigateToRelatedSegment(segmentId: string) {
    const savedCitationId = selectedCitationId;
    const savedReferenceId = selectedReferenceId;
    const savedScrollTop = scrollContainerRef.current?.scrollTop ?? 0;
    const savedExpandedSections = expandedSections;
    setOpen(false);
    onNavigateToSegment(segmentId, () => {
      setSelectedCitationId(savedCitationId);
      setSelectedReferenceId(savedReferenceId);
      setExpandedSections(savedExpandedSections);
      restoreScrollTopRef.current = savedScrollTop;
      setOpen(true);
    });
  }

  function disclosureProps(key: string) {
    return {
      open: expandedSections[key] ?? false,
      onOpenChange: (value: boolean) => setExpandedSections((current) => ({ ...current, [key]: value })),
    };
  }

  if (citations.length === 0) return null;

  return (
    <section className="mt-6 rounded-2xl border border-slate-900/10 bg-white p-5" aria-label="本段參考文獻">
      <div className="flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <BookOpenText className="size-4 text-indigo-700" />本段參考文獻
        </h3>
        <span className="text-xs text-slate-500">{citations.length} 處引用</span>
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-500">點開查看摘要、引用脈絡與書目來源。</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {citations.map((entry) => (
          <Button key={entry.id} type="button" variant="outline" size="sm" className="h-auto whitespace-normal py-2 text-left" onClick={() => openCitation(entry)}>
            {entry.label}{entry.matchStatus === "ambiguous" ? " · 待辨識" : ""}<ArrowRight className="shrink-0" />
          </Button>
        ))}
      </div>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent className="w-[min(96vw,680px)] gap-0 sm:max-w-[680px]" onOpenAutoFocus={(event) => {
          if (restoreScrollTopRef.current === null) return;
          event.preventDefault();
          scrollContainerRef.current?.focus({ preventScroll: true });
          if (scrollContainerRef.current) scrollContainerRef.current.scrollTop = restoreScrollTopRef.current;
          restoreScrollTopRef.current = null;
        }}>
          <SheetHeader className="shrink-0 border-b pr-12">
            <SheetTitle>參考文獻與引用關係</SheetTitle>
            <SheetDescription>文獻摘要直接顯示可核對摘要的繁中翻譯，無須取得全文；本文引用關係另行說明。</SheetDescription>
          </SheetHeader>
          <div ref={scrollContainerRef} tabIndex={-1} className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-7">
            {!reference && citation && (
              <div>
                <Badge className="bg-amber-100 text-amber-950">引用身分待確認</Badge>
                <h2 className="mt-4 font-serif text-xl font-semibold">{citation.label}</h2>
                <p className="mt-3 text-sm leading-7 text-slate-600">同作者、同年份對應到多筆書目。目前無法確定作者指的是哪一篇，請核對下列候選文獻。</p>
                <div className="mt-5 space-y-3">
                  {citation.referenceIds.map((id) => {
                    const candidate = paper.references?.find((entry) => entry.id === id);
                    return candidate ? (
                      <button key={id} type="button" className="w-full rounded-xl border border-slate-200 bg-slate-50 p-4 text-left transition hover:border-indigo-300 focus-visible:ring-2 focus-visible:ring-indigo-500" onClick={() => setSelectedReferenceId(id)}>
                        <p className="text-xs text-slate-500">{candidate.label}</p>
                        <p className="mt-1 text-sm font-semibold leading-6">{candidate.title}</p>
                        <p className="mt-2 text-xs leading-5 text-slate-500">{candidate.authors}</p>
                      </button>
                    ) : null;
                  })}
                </div>
              </div>
            )}

            {reference && citation && (
              <div className="space-y-6">
                {citation.matchStatus === "ambiguous" && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-950">
                    這是候選文獻，尚未確認與此處引用相符。
                    <Button type="button" variant="ghost" size="sm" className="mt-2 block" onClick={() => setSelectedReferenceId(null)}><ArrowLeft />返回候選清單</Button>
                  </div>
                )}
                <div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary">文末書目 · 自動擷取待核對</Badge>
                    <Badge variant="outline">PDF 第 {pagesLabel(reference)} 頁</Badge>
                  </div>
                  <h2 className="mt-4 font-serif text-2xl font-semibold leading-9">{reference.title}</h2>
                  <p className="mt-3 text-sm leading-7 text-slate-600">{reference.authors}（{reference.year}）</p>
                  {reference.doi && <p className="mt-2 break-all text-xs leading-5 text-slate-500">DOI：{reference.doi}</p>}
                  {reference.doiResolution && <p className="mt-2 text-xs leading-5 text-slate-500">依標題、作者與年份查核補齊 DOI。{reference.printedDoi && reference.printedDoi !== reference.doi ? `原書目 DOI：${reference.printedDoi}（與標題不符，未採用）` : "原始書目保留於下方。"}</p>}
                  {reference.identityStatus === "title-mismatch" && <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-950">文末書目標題與 DOI 紀錄不一致，已停止套用摘要，需先人工核對文獻身分。</p>}
                </div>

                <section className="rounded-2xl border border-indigo-200 bg-indigo-50/60 p-5" data-reference-abstract-card>
                  <h3 className="font-serif text-xl font-semibold">文獻摘要 · Abstract</h3>
                  {reference.abstract.status === "available" ? (
                    <>
                      <Badge className="mt-3 bg-indigo-700">{reference.abstract.faithfulZh ? ((reference.abstract.sourceType === "eric" && reference.abstract.abstractOrigin !== "As Provided") || reference.abstract.sourceType === "openaire" || reference.abstract.sourceType === "ebsco" ? "資料庫摘要完整翻譯 · AI 草稿" : "Abstract 忠實翻譯 · AI 草稿") : "已取得摘要 · 忠實翻譯尚未完成"}</Badge>
                      {reference.abstract.faithfulZh ? <p className="mt-4 whitespace-pre-wrap text-base leading-8 text-slate-800" data-abstract-faithful-translation>{reference.abstract.faithfulZh}</p> : <p className="mt-4 text-sm leading-7 text-slate-600">已取得來源摘要，但完整 Abstract 的繁中翻譯尚未完成。不使用重點整理替代忠實翻譯。</p>}
                      <Collapsible {...disclosureProps("abstract-excerpt")} className="mt-4 rounded-xl border border-indigo-200 bg-white">
                        <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold">核對摘要原文節錄<ChevronDown className="size-4" /></CollapsibleTrigger>
                        <CollapsibleContent className="border-t border-indigo-100 px-4 py-4 font-serif text-sm leading-7 text-slate-700"><p data-abstract-source-text>{reference.abstract.originalText.replace(/^Abstract\s+/i, "")}</p></CollapsibleContent>
                      </Collapsible>
                      <p className="mt-3 text-xs leading-5 text-slate-500">翻譯依據：{abstractSourceLabel(reference)}。未讀取被引文獻全文。{reference.abstract.checkedAt ? `來源查核：${reference.abstract.checkedAt.slice(0, 10)}` : ""}</p>
                      {sourceUrl && <Collapsible {...disclosureProps("source-record")} className="mt-3 text-xs text-slate-500"><CollapsibleTrigger className="flex w-full items-center justify-between gap-2 py-2 text-left">來源查核記錄<ChevronDown className="size-3 shrink-0" /></CollapsibleTrigger><CollapsibleContent><p className="break-all leading-5" data-abstract-source-url>{sourceUrl}</p></CollapsibleContent></Collapsible>}
                      {reference.abstract.summaryZh && <Collapsible {...disclosureProps("legacy-summary")} className="mt-5 rounded-xl border border-indigo-200 bg-white">
                        <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-4 py-3 text-sm font-semibold">舊版重點整理 · 非忠實翻譯<ChevronDown className="size-4 shrink-0" /></CollapsibleTrigger>
                        <CollapsibleContent className="border-t border-indigo-100 px-4 py-4">
                          <p className="text-sm leading-7 text-slate-700">{reference.abstract.summaryZh}</p>
                          <p className="mt-3 text-xs leading-5 text-slate-500">{reference.abstract.summaryMethod === "extractive-translation" ? "這是選取摘要原句後的重點摘譯，不是完整摘要，也不保證涵蓋所有結果。" : "這是根據來源摘要整理的中文輔助內容，並非作者的 Abstract 原文或經人工校訂的全文翻譯。"}</p>
                        </CollapsibleContent>
                      </Collapsible>}
                    </>
                  ) : (
                    <div className="mt-4 text-sm leading-7 text-slate-600">
                      <p>此文獻的摘要尚未完成取得與翻譯；完成後會直接顯示在此處，不需要離開閱讀器。</p>
                      {reference.abstract.retrievalReason && <p className="mt-2" data-abstract-retrieval-reason>{reference.abstract.retrievalReason}</p>}
                      <p className="mt-2">不會根據標題或本文引用句補寫成原論文摘要。</p>
                    </div>
                  )}
                </section>

                <section className="rounded-2xl border border-emerald-200 bg-emerald-50/70 p-5">
                  <h3 className="font-serif text-xl font-semibold">與這篇論文的關係</h3>
                  <Badge className="mt-3 bg-emerald-700">本文引用脈絡 · 非被引文獻摘要</Badge>
                  <p className="mt-4 text-base leading-8 text-slate-800">{citation.relationshipZh || (citedSegment.paragraphAssessment?.status === "fragment" ? citation.sourceContext : citedSegment.translation.plainZh || citedSegment.translation.faithfulZh || citation.sourceContext)}</p>
                  {citedSegment.paragraphAssessment?.status === "fragment" && <p className="mt-2 text-xs leading-5 text-amber-800">引用所在閱讀單位是待重建片段；不以舊片段白話稿當作完整段落解釋，引用關係仍需對照原句。</p>}
                  <p className="mt-3 text-xs leading-5 text-slate-500">{citation.relationshipZh ? "以上依本文引用原句整理文獻的角色，屬 AI 草稿，並非被引文獻作者對本文的評論。" : citedSegment.paragraphAssessment?.status === "fragment" ? "以上只保留本文引用原句；所在單位尚不完整，不據此推斷整段主張或製作獨立段落解釋。" : "以上是引用所在段落的白話整理，保留整段脈絡；多篇文獻合併引用時，不將整段主張歸給單一文獻。"}</p>
                  <Collapsible {...disclosureProps("citation-context")} className="mt-4 rounded-xl border border-emerald-200 bg-white">
                    <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold">本文如何引用：原句與頁碼<ChevronDown className="size-4" /></CollapsibleTrigger>
                    <CollapsibleContent className="border-t border-emerald-100 px-4 py-4">
                      <p className="text-xs text-slate-500">PDF 第 {[...new Set(citedSegment.fragments.map((fragment) => fragment.page))].join("、")} 頁</p>
                      <p className="mt-2 font-serif text-sm leading-7 text-slate-700">{citation.sourceContext}</p>
                    </CollapsibleContent>
                  </Collapsible>
                </section>

                <section>
                  <h3 className="text-sm font-semibold">本文中引用這篇文獻的段落</h3>
                  <div className="mt-3 space-y-2">
                    {relatedSegmentIds.map((id) => {
                      const entry = paper.segments.find((value) => value.id === id && !value.excluded);
                      return entry ? <Button key={id} type="button" variant="outline" data-reference-segment-id={id} className="h-auto w-full justify-between whitespace-normal px-4 py-3 text-left" onClick={() => navigateToRelatedSegment(id)}><span className="line-clamp-2 text-sm leading-6">第 {entry.order} 段 · {entry.section}</span><ArrowRight className="shrink-0" /></Button> : null;
                    })}
                    {relatedSegmentIds.length === 0 && <p className="text-sm leading-7 text-slate-500">此候選文獻尚無確定對應的正文引用。</p>}
                  </div>
                </section>

                <Collapsible {...disclosureProps("bibliography")} className="rounded-xl border border-slate-200">
                  <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-sm font-semibold">完整文末書目<ChevronDown className="size-4" /></CollapsibleTrigger>
                  <CollapsibleContent className="border-t border-slate-200 px-4 py-4 text-xs leading-6 text-slate-600">{reference.sourceText}</CollapsibleContent>
                </Collapsible>
                <div className="flex flex-wrap gap-2 pb-6">
                  <Button asChild variant="outline" size="sm"><a href={`${publicAssetUrl(paper.pdfUrl)}#page=${reference.fragments[0].page}`} target="_blank" rel="noreferrer">核對 PDF 書目<ExternalLink /></a></Button>
                  {reference.doi && <Button asChild variant="outline" size="sm"><a href={`https://doi.org/${encodeURIComponent(reference.doi)}`} target="_blank" rel="noreferrer">開啟原文來源<ExternalLink /></a></Button>}
                </div>
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>
    </section>
  );
}
