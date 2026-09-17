"use client";

import { publicAssetUrl } from "@/lib/public-asset-url";
import NextImage from "next/image";
import { useCallback, useEffect, useRef, useState, type ReactNode, type PointerEvent, type KeyboardEvent } from "react";
import { GripHorizontal, Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { PaperExhibit } from "@/lib/paper-types";
import { clampWindowOffset, type WindowOffset } from "@/lib/exhibit-window-position";

export function ExhibitLinkedText({ text, exhibits, onOpen }: {
  text: string;
  exhibits: PaperExhibit[];
  onOpen?: (exhibitId: string) => void;
}) {
  if (!onOpen) return <>{text}</>;
  const pattern = /(?:\b(Table|Tables|Fig(?:ure)?s?\.?)|([表圖]))\s*(\d+)(?!\d)/gi;
  const parts: ReactNode[] = [];
  let previous = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index;
    const kind = match[2] === "表" || match[1]?.toLowerCase().startsWith("table") ? "table" : "figure";
    const exhibit = exhibits.find(entry => entry.kind === kind && entry.number === match[3]);
    if (!exhibit) continue;
    parts.push(text.slice(previous, index));
    parts.push(<button key={index} type="button" data-exhibit-mention={exhibit.id}
      aria-label={`查看 ${exhibit.label}（不離開目前段落）`}
      onClick={() => onOpen(exhibit.id)}
      className="inline rounded-sm font-inherit text-blue-700 underline decoration-blue-400 underline-offset-4 hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">{match[0]}</button>);
    previous = index + match[0].length;
  }
  parts.push(text.slice(previous));
  return <>{parts}</>;
}

export function ExhibitPreview({ exhibit, onClose }: { exhibit: PaperExhibit; onClose: () => void }) {
  const [zoom, setZoom] = useState(1);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [offset, setOffset] = useState<WindowOffset>({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const windowRef = useRef<HTMLDivElement>(null);
  const [windowElement, setWindowElement] = useState<HTMLDivElement | null>(null);
  // Radix mounts portal contents after the first render; observe the actual node,
  // not an initially null ref in a one-time effect.
  const bindWindow = useCallback((node: HTMLDivElement | null) => {
    windowRef.current = node;
    setWindowElement(node);
  }, []);
  const offsetRef = useRef(offset);
  const dragRef = useRef<{ id: number; x: number; y: number; origin: WindowOffset } | null>(null);

  function moveTo(next: WindowOffset) {
    const rect = windowRef.current?.getBoundingClientRect();
    const bounded = rect ? clampWindowOffset(next, rect, { width: window.innerWidth, height: window.innerHeight }) : next;
    offsetRef.current = bounded;
    setOffset(bounded);
  }

  useEffect(() => {
    const element = windowElement;
    if (!element) return;
    const bound = () => {
      const rect = element.getBoundingClientRect();
      const next = clampWindowOffset(offsetRef.current, rect, { width: window.innerWidth, height: window.innerHeight });
      if (next.x !== offsetRef.current.x || next.y !== offsetRef.current.y) {
        offsetRef.current = next;
        setOffset(next);
      }
    };
    const observer = new ResizeObserver(bound);
    observer.observe(element);
    window.addEventListener("resize", bound);
    window.visualViewport?.addEventListener("resize", bound);
    bound();
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", bound);
      window.visualViewport?.removeEventListener("resize", bound);
    };
  }, [windowElement]);

  function startDrag(event: PointerEvent<HTMLDivElement>) {
    if (!event.isPrimary || event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { id: event.pointerId, x: event.clientX, y: event.clientY, origin: offsetRef.current };
    setDragging(true);
    event.preventDefault();
  }

  function drag(event: PointerEvent<HTMLDivElement>) {
    const start = dragRef.current;
    if (!start || start.id !== event.pointerId) return;
    moveTo({ x: start.origin.x + event.clientX - start.x, y: start.origin.y + event.clientY - start.y });
  }

  function endDrag(event: PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.id !== event.pointerId) return;
    dragRef.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }

  function moveWithKeyboard(event: KeyboardEvent<HTMLButtonElement>) {
    const directions: Record<string, WindowOffset> = {
      ArrowLeft: { x: -1, y: 0 }, ArrowRight: { x: 1, y: 0 },
      ArrowUp: { x: 0, y: -1 }, ArrowDown: { x: 0, y: 1 },
    };
    const direction = directions[event.key];
    if (!direction) return;
    event.preventDefault();
    event.stopPropagation();
    const step = event.shiftKey ? 40 : 10;
    moveTo({ x: offsetRef.current.x + direction.x * step, y: offsetRef.current.y + direction.y * step });
  }
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent ref={bindWindow} style={{ left: `calc(50% + ${offset.x}px)`, top: `calc(50% + ${offset.y}px)` }}
      className="flex max-h-[90dvh] flex-col overflow-hidden sm:max-w-[min(1100px,calc(100vw-2rem))]" data-exhibit-preview={exhibit.id}>
      <div data-exhibit-drag-region className={`shrink-0 touch-none select-none pr-8 ${dragging ? "cursor-grabbing" : "cursor-grab"}`}
        onPointerDown={startDrag} onPointerMove={drag} onPointerUp={endDrag} onPointerCancel={endDrag} onLostPointerCapture={endDrag}>
      <DialogHeader>
        <DialogTitle>{exhibit.label} · {exhibit.kind === "table" ? "表" : "圖"} {exhibit.number}</DialogTitle>
        <DialogDescription>原始 PDF 第 {exhibit.page} 頁。關閉後留在目前段落，不更改閱讀位置或筆記。</DialogDescription>
      </DialogHeader>
      <button type="button" data-exhibit-drag-handle aria-label="移動圖表視窗，可拖曳標題列或使用方向鍵" onKeyDown={moveWithKeyboard}
        className="mt-2 flex items-center gap-1 rounded text-xs text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2">
        <GripHorizontal className="size-4" aria-hidden="true" />拖曳標題列移動 · 方向鍵亦可移動
      </button>
      </div>
      <div className="flex shrink-0 items-center justify-between gap-3">
        <p className="text-sm leading-6">{exhibit.captionZh || exhibit.caption}</p>
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="outline" size="sm" aria-label="將圖表視窗置中" onClick={() => moveTo({ x: 0, y: 0 })}>置中</Button>
          <Button variant="outline" size="icon-sm" aria-label="縮小圖表" disabled={zoom <= 1} onClick={() => setZoom(value => Math.max(1, value - 0.25))}><Minus /></Button>
          <span className="w-12 text-center text-xs">{Math.round(zoom * 100)}%</span>
          <Button variant="outline" size="icon-sm" aria-label="放大圖表" disabled={zoom >= 3} onClick={() => setZoom(value => Math.min(3, value + 0.25))}><Plus /></Button>
        </div>
      </div>
      <div className="min-h-0 overflow-auto rounded-lg border bg-white" tabIndex={0} aria-label={`${exhibit.label} 原始圖表，可捲動查看`}>
        {failed ? <div role="alert" className="p-6 text-sm text-red-800">圖表圖片載入失敗，未改動目前閱讀位置。<Button className="ml-3" variant="outline" onClick={() => { setFailed(false); setRetry(value => value + 1); }}>重試載入</Button></div> :
          <NextImage src={publicAssetUrl(exhibit.imageUrl) + (retry ? `?retry=${retry}` : "")} alt={`${exhibit.label}：${exhibit.captionZh || exhibit.caption}`}
            width={Math.round((exhibit.bbox[2] - exhibit.bbox[0]) * 300 / 72)} height={Math.round((exhibit.bbox[3] - exhibit.bbox[1]) * 300 / 72)}
            unoptimized className="h-auto max-w-none" style={{ width: `${zoom * 100}%` }} onError={() => setFailed(true)} />}
      </div>
      <div className="flex shrink-0 justify-end"><DialogClose asChild><Button variant="outline">關閉，繼續閱讀</Button></DialogClose></div>
    </DialogContent>
  </Dialog>;
}
