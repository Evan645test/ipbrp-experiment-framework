import type { ExhibitCompanionLink, PaperDocument, PaperSegment } from "@/lib/paper-types";

export type ExhibitDock = "translation" | "source" | "floating";
export interface CompanionState {
  version: 1;
  paperId: string;
  sourceSha256: string;
  layout: { dock: ExhibitDock; width: number; height: number; x: number; y: number; mobileHeight: number };
  zooms: Record<string, number>;
  corrections: Record<string, Record<string, "include" | "exclude">>;
}

export function companionStorageKey(paperId: string) { return `paper-focus-companion:v1:${paperId}`; }
export function emptyCompanionState(paper: PaperDocument): CompanionState {
  return { version: 1, paperId: paper.id, sourceSha256: paper.sourceSha256,
    layout: { dock: "translation", width: 420, height: 380, x: 32, y: 100, mobileHeight: 340 }, zooms: {}, corrections: {} };
}

export function readingSegments(paper: PaperDocument): PaperSegment[] {
  const captions = new Set(paper.exhibits?.map(e => e.captionSegmentId));
  return paper.segments.filter(s => !s.excluded && (!paper.readingQuality || !s.readingRole) && (!paper.exhibitCompanion || (s.kind !== "caption" && !captions.has(s.id))));
}

export function resolveReadingSegment(paper: PaperDocument, previousId: string | null | undefined): PaperSegment | undefined {
  const included = readingSegments(paper);
  const direct = included.find(s => s.id === previousId);
  if (direct) return direct;
  const old = paper.segments.find(s => s.id === previousId);
  const merged = included.find(s => s.id === old?.mergedIntoSegmentId);
  if (merged) return merged;
  if (paper.exhibitCompanion) {
    const exhibit = paper.exhibits?.find(e => e.captionSegmentId === previousId || e.captionSegmentId === old?.mergedIntoSegmentId);
    const link = exhibit && paper.exhibitCompanion.links.find(l => l.exhibitId === exhibit.id && l.confidence === "high" && included.some(s => s.id === l.segmentId));
    if (link) return included.find(s => s.id === link.segmentId);
  }
  return old ? included.find(s => s.order >= old.order) ?? included.at(-1) : included[0];
}

export function validateCompanionState(value: unknown, paper: PaperDocument): CompanionState {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("伴讀備份不是有效物件。");
  const v = value as CompanionState;
  if (v.version !== 1 || v.paperId !== paper.id || v.sourceSha256 !== paper.sourceSha256) throw new Error("伴讀備份不屬於目前論文或 PDF 版本。");
  const layout = v.layout;
  if (!layout || !["translation", "source", "floating"].includes(layout.dock)) throw new Error("伴讀位置設定無效。");
  for (const key of ["width", "height", "x", "y", "mobileHeight"] as const) {
    if (typeof layout[key] !== "number" || !Number.isFinite(layout[key])) throw new Error("伴讀尺寸或位置無效。");
  }
  if (layout.width < 280 || layout.width > 1600 || layout.height < 180 || layout.height > 1400 || layout.mobileHeight < 140 || layout.mobileHeight > 800 || Math.abs(layout.x) > 10000 || Math.abs(layout.y) > 10000) throw new Error("伴讀尺寸或位置超出範圍。");
  const exhibits = new Set(paper.exhibits?.map(e => e.id));
  // Archived local corrections remain in backups but are not applied to non-body content.
  const segments = new Set(paper.segments.map(s => s.id));
  const zooms: Record<string, number> = {};
  if (!v.zooms || typeof v.zooms !== "object" || Array.isArray(v.zooms)) throw new Error("圖片縮放設定無效。");
  for (const [id, zoom] of Object.entries(v.zooms)) {
      if (!exhibits.has(id) || typeof zoom !== "number" || !Number.isFinite(zoom) || zoom < 0.5 || zoom > 4) throw new Error("圖片縮放設定無效。");
    zooms[id] = zoom;
  }
  if (!v.corrections || typeof v.corrections !== "object" || Array.isArray(v.corrections)) throw new Error("關聯修正格式無效。");
  const corrections: CompanionState["corrections"] = {};
  for (const [segmentId, entries] of Object.entries(v.corrections)) {
    if (!segments.has(segmentId) || !entries || typeof entries !== "object" || Array.isArray(entries)) throw new Error("關聯修正包含不存在的正文段落。");
    const valid: Record<string, "include" | "exclude"> = {};
    for (const [id, action] of Object.entries(entries)) {
      if (!exhibits.has(id) || !["include", "exclude"].includes(action)) throw new Error("關聯修正包含不存在的圖表或無效操作。");
      valid[id] = action;
    }
    corrections[segmentId] = valid;
  }
  return { version: 1, paperId: paper.id, sourceSha256: paper.sourceSha256, layout: { ...layout }, zooms, corrections };
}

export function loadCompanionState(paper: PaperDocument): CompanionState {
  try {
    const text = window.localStorage.getItem(companionStorageKey(paper.id));
    return text ? validateCompanionState(JSON.parse(text), paper) : emptyCompanionState(paper);
  } catch { return emptyCompanionState(paper); }
}

export function effectiveCompanionLinks(paper: PaperDocument, segment: PaperSegment, state: CompanionState) {
  const corrections = Object.assign({}, ...paper.segments.filter(s => s.mergedIntoSegmentId === segment.id).map(s => state.corrections[s.id] ?? {}), state.corrections[segment.id] ?? {}) as Record<string, "include" | "exclude">;
  // Do not inherit generated relationships after a local curator changed source text.
  const originals = (paper.exhibitCompanion?.links ?? []).filter(l => l.segmentId === segment.id && segment.sourceText === l.evidenceQuote);
  const accepted = originals.filter(l => corrections[l.exhibitId] !== "exclude" && (l.confidence === "high" || corrections[l.exhibitId] === "include"))
    .map(l => l.confidence === "candidate" ? { ...l, confidence: "high" as const,
      relationshipZh: "你已確認將此語意候選加入本段伴讀；這是本機人工關聯，不代表作者明確引用。原候選依據：" + l.relationshipZh } : l);
  for (const [id, action] of Object.entries(corrections)) {
    if (action !== "include" || accepted.some(l => l.exhibitId === id)) continue;
    const e = paper.exhibits?.find(e => e.id === id);
    if (e) accepted.push({ segmentId: segment.id, exhibitId: id, method: "semantic", confidence: "high",
      relationshipZh: "你已將這張圖表加入本段伴讀；此關聯為本機人工選擇，不代表作者明確引用。",
      evidenceQuote: segment.sourceText, sourceSegmentIds: [segment.id], sourceTextSha256: "" } satisfies ExhibitCompanionLink);
  }
  const candidates = originals.filter(l => l.confidence === "candidate" && !corrections[l.exhibitId]);
  return { accepted, candidates };
}

/** Use the same validated/local-corrected links as paragraph reading, never raw candidates. */
export function exhibitOverviewPassages(paper: PaperDocument, exhibitId: string, state: CompanionState) {
  return readingSegments(paper).flatMap(segment => {
    const link = effectiveCompanionLinks(paper, segment, state).accepted.find(item => item.exhibitId === exhibitId);
    return link ? [{ segment, link, label: state.corrections[segment.id]?.[exhibitId] === "include"
      ? "使用者加入" : link.method === "explicit" ? "明確引用" : "語意關聯" }] : [];
  }).sort((a, b) => a.segment.order - b.segment.order);
}
