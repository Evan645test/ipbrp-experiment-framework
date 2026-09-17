import type { PaperDocument, PaperSegment } from "@/lib/paper-types";

const CURATOR_PREFIX = "paper-focus-curator:v1:";

export function curatorStorageKey(paperId: string): string {
  return `${CURATOR_PREFIX}${paperId}`;
}

export function renumberSegments(segments: PaperSegment[]): PaperSegment[] {
  return segments.map((segment, index) => ({ ...segment, order: index + 1 }));
}

function finiteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function validateCuratedPaper(
  value: unknown,
  source: PaperDocument,
): PaperDocument {
  if (!value || typeof value !== "object") throw new Error("檔案不是有效的 JSON 物件。");
  const paper = value as Partial<PaperDocument>;
  if (paper.schemaVersion !== source.schemaVersion) throw new Error("資料格式版本不相容。");
  if (paper.id !== source.id) throw new Error("這份校編稿不屬於目前論文。");
  if (paper.sourceSha256 !== source.sourceSha256) throw new Error("校編稿與目前 PDF 版本不同。");
  if (!Array.isArray(paper.segments) || paper.segments.length === 0) throw new Error("校編稿沒有任何段落。");
  if (!paper.segments.some((segment) => !segment.excluded)) throw new Error("至少必須保留一段納入讀者閱讀順序。");

  const ids = new Set<string>();
  paper.segments.forEach((segment, index) => {
    if (!segment || typeof segment !== "object") throw new Error(`第 ${index + 1} 段格式錯誤。`);
    if (typeof segment.id !== "string" || !segment.id.trim()) throw new Error(`第 ${index + 1} 段缺少 ID。`);
    if (ids.has(segment.id)) throw new Error(`段落 ID 重複：${segment.id}`);
    ids.add(segment.id);
    if (typeof segment.sourceText !== "string" || !segment.sourceText.trim()) throw new Error(`第 ${index + 1} 段缺少原文。`);
    if (!Array.isArray(segment.fragments) || segment.fragments.length === 0) throw new Error(`第 ${index + 1} 段缺少 PDF 位置。`);
    segment.fragments.forEach((fragment) => {
      if (!Number.isInteger(fragment.page) || fragment.page < 1 || fragment.page > source.pageCount) {
        throw new Error(`第 ${index + 1} 段的 PDF 頁碼超出範圍。`);
      }
      if (
        !Array.isArray(fragment.bbox) || fragment.bbox.length !== 4 ||
        !fragment.bbox.every(finiteNumber) || !Array.isArray(fragment.pageSize) ||
        fragment.pageSize.length !== 2 || !fragment.pageSize.every(finiteNumber)
      ) {
        throw new Error(`第 ${index + 1} 段的 PDF 座標無效。`);
      }
      const [x0, y0, x1, y1] = fragment.bbox;
      const [width, height] = fragment.pageSize;
      if (x0 < 0 || y0 < 0 || x1 <= x0 || y1 <= y0 || x1 > width || y1 > height) {
        throw new Error(`第 ${index + 1} 段的 PDF 座標超出頁面。`);
      }
    });
    if (!segment.translation || typeof segment.translation !== "object") throw new Error(`第 ${index + 1} 段缺少翻譯狀態。`);
    if (!["untranslated", "ai-draft", "reviewed"].includes(segment.translation.status)) {
      throw new Error(`第 ${index + 1} 段的翻譯狀態無效。`);
    }
    if (segment.translation.status === "reviewed" && (!segment.translation.faithfulZh.trim() || !segment.translation.plainZh.trim())) {
      throw new Error(`第 ${index + 1} 段標為已校訂，但翻譯或白話說明為空。`);
    }
  });

  return {
    ...source,
    ...paper,
    publicationStatus: "draft",
    segments: renumberSegments(paper.segments),
  } as PaperDocument;
}

export function loadCuratorDraft(source: PaperDocument): PaperDocument {
  try {
    const raw = window.localStorage.getItem(curatorStorageKey(source.id));
    if (!raw) return source;
    const stored = JSON.parse(raw) as PaperDocument;
    const curated = validateCuratedPaper(stored, source);
    const sourceSegments = new Map(source.segments.map((segment) => [segment.id, segment]));
    let segments = curated.segments;
    const repair = source.readingOrderRepair;
    if (repair && stored.readingOrderRepair?.revision !== repair.revision) {
      const local = new Map(segments.map((segment) => [segment.id, segment]));
      const oldOrder = repair.previousSegmentIds;
      const isOldGeneratedOrder = segments.length === oldOrder.length &&
        segments.every((segment, index) => segment.id === oldOrder[index]);
      if (isOldGeneratedOrder) {
        segments = source.segments.map((segment) => local.get(segment.id) ?? segment);
      } else {
        // Preserve deliberate local moves/merges/deletions. Insert only newly
        // recovered records, not records the user removed from their draft.
        segments = [...segments];
        const previousIds = new Set(oldOrder);
        source.segments.forEach((segment, index) => {
          if (local.has(segment.id) || previousIds.has(segment.id)) return;
          const nextIds = new Set(source.segments.slice(index + 1).map((entry) => entry.id));
          const nextIndex = segments.findIndex((entry) => nextIds.has(entry.id));
          segments.splice(nextIndex < 0 ? segments.length : nextIndex, 0, segment);
        });
      }
    }
    const pendingRepairs: string[] = [];
    const blockedAbsorbed = new Set<string>();
    for (const unitRepair of source.readingUnitRepairs ?? []) {
      const target = segments.find(segment => segment.id === unitRepair.targetId);
      const current = sourceSegments.get(unitRepair.targetId);
      if (!target || !current) continue;
      const alreadyUpdated = target.sourceText === current.sourceText &&
        JSON.stringify(target.fragments) === JSON.stringify(current.fragments);
      const untouched = unitRepair.previousSegments.every(previous => {
        const local = segments.find(segment => segment.id === previous.id);
        return local && local.sourceText === previous.sourceText &&
          JSON.stringify(local.fragments) === JSON.stringify(previous.fragments) &&
          JSON.stringify(local.translation) === JSON.stringify(previous.translation) &&
          !["reviewed", "published"].includes(local.reviewStatus);
      });
      if (!alreadyUpdated && !untouched) {
        pendingRepairs.push(unitRepair.targetId);
        unitRepair.absorbedIds.forEach(id => blockedAbsorbed.add(id));
        continue;
      }
      segments = segments.map(segment => {
        if (segment.id === current.id && untouched && !alreadyUpdated) {
          return { ...current, ...(Object.hasOwn(segment, "excluded") ? { excluded: segment.excluded } : {}) };
        }
        if (unitRepair.absorbedIds.includes(segment.id)) {
          return { ...segment, mergedIntoSegmentId: current.id,
            ...(!Object.hasOwn(segment, "excluded") ? { excluded: true } : {}) };
        }
        return segment;
      });
    }
    const retainedIds = new Set(segments.map(segment => segment.id));
    const quality = source.readingQuality ? {
      ...source.readingQuality,
      explanationRepairs: source.readingQuality.explanationRepairs.filter(r => retainedIds.has(r.segmentId)),
      appendices: source.readingQuality.appendices.filter(a => a.exhibit.captionSegmentId && retainedIds.has(a.exhibit.captionSegmentId)).map(a => ({ ...a, relatedSegmentIds: a.relatedSegmentIds.filter(id => retainedIds.has(id)) })),
    } : undefined;
    return {
      ...curated,
      // Exhibit extraction and links are generated from the current PDF and must
      // not be replaced by an older local curator draft.
      exhibits: source.exhibits,
      references: source.references,
      citations: source.citations,
      readingOrderRepair: source.readingOrderRepair,
      inlineExhibitsEnabled: source.inlineExhibitsEnabled,
      exhibitCompanion: source.exhibitCompanion,
      readingQuality: quality,
      readingUnitRepairs: source.readingUnitRepairs,
      pendingReadingUnitRepairs: pendingRepairs,
      segments: renumberSegments(segments.map((segment) => {
        const current = sourceSegments.get(segment.id);
        const plainRepair = source.readingQuality?.explanationRepairs.find(r => r.segmentId === segment.id);
        return {
          ...segment,
          ...(!Object.hasOwn(segment, "readingRole") && current?.sourceText === segment.sourceText ? { readingRole: current.readingRole, section: current.readingRole ? current.section : segment.section } : {}),
          ...(plainRepair && segment.sourceText === plainRepair.sourceText && JSON.stringify(segment.translation) === JSON.stringify(plainRepair.previousTranslation)
            && !["reviewed", "published"].includes(segment.reviewStatus) ? { translation: current!.translation } : {}),
          // Inherit new cleanup flags only for unchanged, unedited inclusion state.
          // Explicit local include/exclude decisions continue to belong to the user.
          ...(!blockedAbsorbed.has(segment.id) && !Object.hasOwn(segment, "excluded") && current?.sourceText === segment.sourceText
            ? { excluded: current.excluded }
            : {}),
          ...(!blockedAbsorbed.has(segment.id) && !Object.hasOwn(segment, "mergedIntoSegmentId") && current?.sourceText === segment.sourceText && current.mergedIntoSegmentId
            ? { mergedIntoSegmentId: current.mergedIntoSegmentId }
            : {}),
          exhibitIds: current?.exhibitIds ?? segment.exhibitIds,
          exhibitMentions: current?.sourceText === segment.sourceText && JSON.stringify(current.fragments) === JSON.stringify(segment.fragments) ? current.exhibitMentions : undefined,
          ...(current?.sourceText === segment.sourceText && segment.kind === "caption" && current.kind === "body" && /^(?:Table\s+\d+|Fig(?:ure)?\.?\s+\d+)\s+(?:shows|displays|presents|illustrates|represents|depicts)\b/i.test(segment.sourceText) && !["reviewed", "published"].includes(segment.reviewStatus) ? { kind: current.kind } : {}),
          paragraphAssessment: current?.sourceText === segment.sourceText
            ? current.paragraphAssessment
            : undefined,
        };
      })),
    };
  } catch {
    return source;
  }
}

export function saveCuratorDraft(paper: PaperDocument): void {
  window.localStorage.setItem(curatorStorageKey(paper.id), JSON.stringify(paper));
}

export function clearCuratorDraft(paperId: string): void {
  window.localStorage.removeItem(curatorStorageKey(paperId));
}
