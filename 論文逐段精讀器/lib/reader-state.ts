import type { PaperDocument, ReaderPaperState } from "@/lib/paper-types";
import { readingSegments, resolveReadingSegment } from "@/lib/companion-state";

const STORAGE_PREFIX = "paper-focus-reader:v1:";

export function emptyReaderState(paper: PaperDocument): ReaderPaperState {
  const firstSegmentId = readingSegments(paper)[0]?.id ?? null;
  return {
    version: 1,
    paperId: paper.id,
    sourceSha256: paper.sourceSha256,
    currentSegmentId: firstSegmentId,
    seen: firstSegmentId ? [firstSegmentId] : [],
    understood: [],
    bookmarks: [],
    notes: {},
    dimOpacity: 0.74,
    reducedMotion: false,
    highContrast: false,
    updatedAt: new Date().toISOString(),
  };
}

export function storageKey(paperId: string): string {
  return `${STORAGE_PREFIX}${paperId}`;
}

export function loadReaderState(paper: PaperDocument): ReaderPaperState {
  const included = readingSegments(paper);
  const fallback = emptyReaderState({ ...paper, segments: included });
  try {
    const raw = window.localStorage.getItem(storageKey(paper.id));
    if (!raw) return fallback;
    const value = JSON.parse(raw) as Partial<ReaderPaperState>;
    if (value.version !== 1 || value.paperId !== paper.id) return fallback;
    const validIds = new Set(paper.segments.map((segment) => segment.id));
    const readingIds = new Set(included.map((segment) => segment.id));
    const currentSegmentId =
      value.currentSegmentId && readingIds.has(value.currentSegmentId)
        ? value.currentSegmentId
        : resolveReadingSegment(paper, value.currentSegmentId)?.id ?? fallback.currentSegmentId;
    return {
      ...fallback,
      ...value,
      sourceSha256: paper.sourceSha256,
      currentSegmentId,
      seen: currentSegmentId
        ? uniqueIds([...(value.seen ?? []).filter((id) => readingIds.has(id)), currentSegmentId])
        : [],
      understood: (value.understood ?? []).filter((id) => validIds.has(id)),
      bookmarks: (value.bookmarks ?? []).filter((id) => validIds.has(id)),
      notes: Object.fromEntries(
        Object.entries(value.notes ?? {}).filter(
          ([id, note]) => validIds.has(id) && typeof note === "string",
        ),
      ),
    };
  } catch {
    return fallback;
  }
}

function uniqueIds(values: string[]): string[] {
  return [...new Set(values)];
}

export function saveReaderState(state: ReaderPaperState): void {
  window.localStorage.setItem(
    storageKey(state.paperId),
    JSON.stringify({ ...state, updatedAt: new Date().toISOString() }),
  );
}

export function downloadText(
  filename: string,
  text: string,
  type = "text/plain;charset=utf-8",
): void {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function notesAsMarkdown(
  paper: PaperDocument,
  state: ReaderPaperState,
): string {
  const lines = [
    `# ${paper.title}`,
    "",
    `- 來源檔案：${paper.sourceFileName}`,
    `- 來源 SHA-256：\`${paper.sourceSha256}\``,
    `- 匯出時間：${new Date().toISOString()}`,
    "",
  ];
  for (const segment of paper.segments) {
    const note = state.notes[segment.id]?.trim();
    if (!note && !state.bookmarks.includes(segment.id)) continue;
    const pages = [...new Set(segment.fragments.map((fragment) => fragment.page))];
    lines.push(
      `## ${segment.section} · 第 ${pages.join("、")} 頁`,
      "",
      `- 段落 ID：\`${segment.id}\``,
      `- 書籤：${state.bookmarks.includes(segment.id) ? "是" : "否"}`,
      `- 已理解：${state.understood.includes(segment.id) ? "是" : "否"}`,
      "",
    );
    if (note) lines.push(note, "");
  }
  return `${lines.join("\n")}\n`;
}
