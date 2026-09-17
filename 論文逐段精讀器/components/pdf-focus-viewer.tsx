"use client";

import { publicAssetUrl } from "@/lib/public-asset-url";
import { useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, Minus, Plus, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { SegmentFragment, PaperSegment } from "@/lib/paper-types";

type PdfJsModule = typeof import("pdfjs-dist");
type PdfDocumentProxy = import("pdfjs-dist").PDFDocumentProxy;

interface PdfFocusViewerProps {
  pdfUrl: string;
  fragments: SegmentFragment[];
  dimOpacity: number;
  reducedMotion: boolean;
  exhibitMentions?: PaperSegment["exhibitMentions"];
  onOpenExhibit?: (exhibitId: string) => void;
}

interface PageCanvasProps {
  pdfjs: PdfJsModule;
  document: PdfDocumentProxy;
  fragment: SegmentFragment;
  width: number;
  zoom: number;
  dimOpacity: number;
  reducedMotion: boolean;
  exhibitMentions?: PaperSegment["exhibitMentions"];
  onOpenExhibit?: (exhibitId: string) => void;
  autoFocus?: boolean;
}

function PageCanvas({
  pdfjs,
  document,
  fragment,
  width,
  zoom,
  dimOpacity,
  reducedMotion,
  exhibitMentions,
  onOpenExhibit,
  autoFocus = true,
}: PageCanvasProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const [renderedSize, setRenderedSize] = useState<[number, number]>([0, 0]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let renderTask: { cancel: () => void; promise: Promise<unknown> } | null = null;
    let textLayer: { cancel: () => void; render: () => Promise<void> } | null = null;

    async function renderPage() {
      setError(null);
      const page = await document.getPage(fragment.page);
      const baseViewport = page.getViewport({ scale: 1 });
      const fitScale = Math.max(0.2, (width - 32) / baseViewport.width);
      const viewport = page.getViewport({ scale: fitScale * zoom });
      const canvas = canvasRef.current;
      const textContainer = textLayerRef.current;
      if (!canvas || !textContainer || cancelled) return;

      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      const context = canvas.getContext("2d", { alpha: false });
      if (!context) throw new Error("無法建立 PDF 畫布。");
      renderTask = page.render({
        canvas,
        canvasContext: context,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      await renderTask.promise;
      if (cancelled) return;

      textContainer.replaceChildren();
      textContainer.style.width = `${viewport.width}px`;
      textContainer.style.height = `${viewport.height}px`;
      const textContent = await page.getTextContent();
      textLayer = new pdfjs.TextLayer({
        textContentSource: textContent,
        container: textContainer,
        viewport,
      });
      await textLayer.render();
      if (!cancelled) setRenderedSize([viewport.width, viewport.height]);
    }

    void renderPage().catch((cause: unknown) => {
      if (
        cancelled ||
        (cause instanceof Error && cause.name === "RenderingCancelledException")
      ) {
        return;
      }
      setError(cause instanceof Error ? cause.message : "PDF 頁面載入失敗。");
    });
    return () => {
      cancelled = true;
      renderTask?.cancel();
      textLayer?.cancel();
    };
  }, [document, fragment, pdfjs, width, zoom]);

  useEffect(() => {
    if (!autoFocus || !renderedSize[0]) return;
    const stage = stageRef.current;
    if (!stage) return;
    const scale = renderedSize[0] / fragment.pageSize[0];
    const focusX = ((fragment.bbox[0] + fragment.bbox[2]) / 2) * scale;
    const focusY = ((fragment.bbox[1] + fragment.bbox[3]) / 2) * scale;
    const scroller = stage.closest<HTMLElement>("[data-pdf-scroller]");
    if (scroller) {
      scroller.scrollTo({
        left: Math.max(0, onOpenExhibit ? stage.offsetLeft + fragment.bbox[0] * scale - 20 : stage.offsetLeft + focusX - scroller.clientWidth / 2),
        top: Math.max(0, stage.offsetTop + focusY - scroller.clientHeight / 2),
        behavior: reducedMotion ? "auto" : "smooth",
      });
    }
  }, [autoFocus, fragment, onOpenExhibit, reducedMotion, renderedSize]);

  if (error) {
    return (
      <div className="mx-auto w-full max-w-2xl rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-900">
        <strong className="block font-semibold">PDF 頁面載入失敗</strong>
        <span className="mt-1 block">{error}</span>
      </div>
    );
  }

  const [pageWidth, pageHeight] = renderedSize;
  const scale = pageWidth ? pageWidth / fragment.pageSize[0] : 1;
  const [x0, y0, x1, y1] = fragment.bbox.map((value) => value * scale);

  return (
    <article
      ref={stageRef}
      className="pdf-page-stage"
      aria-label={`PDF 第 ${fragment.page} 頁的目前段落`}
      style={{ width: pageWidth || "100%", height: pageHeight || 720 }}
    >
      {!pageWidth && (
        <div className="absolute inset-0 grid place-items-center text-sm text-slate-500">
          <span>
            <LoaderCircle className="mr-2 inline size-4 animate-spin" />
            正在排版第 {fragment.page} 頁
          </span>
        </div>
      )}
      <canvas ref={canvasRef} className="absolute inset-0 bg-white" />
      <div ref={textLayerRef} className="textLayer absolute inset-0" />
      {pageWidth > 0 && onOpenExhibit && exhibitMentions?.filter(mention => mention.page === fragment.page).map((mention, index) => (
        <button key={`${mention.exhibitId}:${index}`} type="button" data-pdf-exhibit-mention={mention.exhibitId}
          aria-label={`原始 PDF：查看 ${mention.label}（不離開目前段落）`}
          title={`點選查看 ${mention.label}`}
          className="absolute z-30 rounded-sm bg-transparent hover:bg-blue-300/20 focus-visible:outline-2 focus-visible:outline-blue-600"
          style={{ left: mention.bbox[0] * scale, top: mention.bbox[1] * scale, width: (mention.bbox[2] - mention.bbox[0]) * scale, height: (mention.bbox[3] - mention.bbox[1]) * scale }}
          onClick={() => onOpenExhibit(mention.exhibitId)} />
      ))}
      {pageWidth > 0 && (
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-20">
          <div
            className="absolute inset-x-0 top-0 bg-slate-950"
            style={{ height: Math.max(0, y0), opacity: dimOpacity }}
          />
          <div
            className="absolute bottom-0 left-0 bg-slate-950"
            style={{ top: y0, width: Math.max(0, x0), opacity: dimOpacity }}
          />
          <div
            className="absolute bottom-0 right-0 bg-slate-950"
            style={{ top: y0, width: Math.max(0, pageWidth - x1), opacity: dimOpacity }}
          />
          <div
            className="absolute inset-x-0 bottom-0 bg-slate-950"
            style={{ top: Math.max(0, y1), opacity: dimOpacity }}
          />
          <div
            className="absolute rounded-sm ring-2 ring-amber-400 ring-offset-2 ring-offset-transparent"
            style={{
              left: x0,
              top: y0,
              width: Math.max(1, x1 - x0),
              height: Math.max(1, y1 - y0),
            }}
          />
        </div>
      )}
      <span className="absolute right-3 top-3 z-30 rounded-full bg-slate-950/80 px-2.5 py-1 text-xs font-semibold text-white">
        {fragment.page}
      </span>
    </article>
  );
}

export function PdfFocusViewer({
  pdfUrl,
  fragments,
  dimOpacity,
  reducedMotion,
  exhibitMentions,
  onOpenExhibit,
}: PdfFocusViewerProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [pdfjs, setPdfjs] = useState<PdfJsModule | null>(null);
  const [document, setDocument] = useState<PdfDocumentProxy | null>(null);
  const [width, setWidth] = useState(720);
  const [zoom, setZoom] = useState(1.35);
  const [error, setError] = useState<string | null>(null);
  const [loadStage, setLoadStage] = useState("正在初始化 PDF 閱讀器");

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.min(1000, Math.max(320, entry.contentRect.width)));
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    let activeTask: import("pdfjs-dist").PDFDocumentLoadingTask | null = null;
    let activeWorker: Worker | null = null;
    const controller = new AbortController();
    async function load() {
      setError(null);
      setDocument(null);
      setLoadStage("正在載入 PDF 引擎");
      const pdfModule = await import("pdfjs-dist");
      if (cancelled) return;
      if (!pdfUrl) throw new Error("論文資料沒有 PDF 網址。");
      setLoadStage("正在讀取 PDF 檔案");
      const response = await fetch(new URL(publicAssetUrl(pdfUrl), window.location.href), { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`PDF 檔案回應 ${response.status}。`);
      }
      const data = new Uint8Array(await response.arrayBuffer());
      if (cancelled) return;
      setLoadStage("正在解析 PDF 頁面");
      activeWorker = new Worker(publicAssetUrl("/pdfjs/pdf.worker.min.mjs"), {
        type: "module",
        name: "paper-focus-pdfjs",
      });
      pdfModule.GlobalWorkerOptions.workerPort = activeWorker;
      activeTask = pdfModule.getDocument({
        data,
        useSystemFonts: true,
      });
      const activeDocument = await activeTask.promise;
      if (!cancelled) {
        setPdfjs(pdfModule);
        setDocument(activeDocument);
      }
    }
    void load().catch((cause: unknown) => {
      if (!cancelled) {
        setError(cause instanceof Error ? cause.message : "PDF 載入失敗。");
      }
    });
    return () => {
      cancelled = true;
      controller.abort();
      if (activeTask) {
        void activeTask.destroy().catch(() => {}).finally(() => activeWorker?.terminate());
      } else {
        activeWorker?.terminate();
      }
    };
  }, [pdfUrl]);

  const uniqueFragments = useMemo(() => {
    const seen = new Set<string>();
    return fragments.filter((fragment) => {
      const key = `${fragment.page}:${fragment.bbox.join(",")}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [fragments]);

  return (
    <section
      ref={hostRef}
      className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[#131b2b]"
    >
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-white/10 px-4 text-white">
        <span className="text-xs font-medium text-slate-300">
          原始 PDF ·{" "}
          {uniqueFragments.length > 1
            ? `跨 ${uniqueFragments.length} 頁段落`
            : `第 ${uniqueFragments[0]?.page ?? "—"} 頁`}
        </span>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-white hover:bg-white/10 hover:text-white"
            onClick={() => setZoom((value) => Math.max(0.85, value - 0.15))}
            aria-label="縮小 PDF"
          >
            <Minus />
          </Button>
          <span className="w-12 text-center text-xs tabular-nums text-slate-300">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-white hover:bg-white/10 hover:text-white"
            onClick={() => setZoom((value) => Math.min(2.4, value + 0.15))}
            aria-label="放大 PDF"
          >
            <Plus />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="text-white hover:bg-white/10 hover:text-white"
            onClick={() => setZoom(1.35)}
            aria-label="重設 PDF 縮放"
          >
            <RotateCcw />
          </Button>
        </div>
      </div>
      <div
        data-pdf-scroller
        className="pdf-scroller min-h-0 flex-1 overflow-auto px-4 py-6"
      >
        {error ? (
          <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center text-center text-white">
            <p className="font-semibold">PDF.js 無法開啟此文件</p>
            <p className="mt-2 max-w-md text-sm text-slate-300">{error}</p>
            <Button asChild variant="secondary" className="mt-5">
              <a href={publicAssetUrl(pdfUrl)} target="_blank" rel="noreferrer">
                使用原始 PDF 備援
              </a>
            </Button>
          </div>
        ) : !pdfjs || !document ? (
          <div className="grid h-full place-items-center text-sm text-slate-300">
            <span>
              <LoaderCircle className="mr-2 inline size-4 animate-spin" />
              {loadStage}
            </span>
          </div>
        ) : (
          <div className="mx-auto flex w-max min-w-full flex-col items-center gap-8">
            {uniqueFragments.map((fragment, index) => (
              <PageCanvas
                key={`${fragment.page}:${fragment.bbox.join("-")}`}
                pdfjs={pdfjs}
                document={document}
                fragment={fragment}
                width={width}
                zoom={zoom}
                dimOpacity={dimOpacity}
                reducedMotion={reducedMotion}
                exhibitMentions={exhibitMentions}
                onOpenExhibit={onOpenExhibit}
                autoFocus={onOpenExhibit ? index === 0 : true}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
