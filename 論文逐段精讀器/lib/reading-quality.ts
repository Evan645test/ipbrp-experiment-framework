import type { PaperDocument, PaperSegment } from "@/lib/paper-types";

/** Deterministic safety checks, not a claim of general semantic correctness. */
export function explanationIssues(paper: PaperDocument, segment: PaperSegment): string[] {
  if (!paper.readingQuality || segment.translation.status === "reviewed") return [];
  const issues: string[] = [];
  const repair = paper.readingQuality.explanationRepairs.find(r => r.segmentId === segment.id);
  if (repair && (repair.sourceText !== segment.sourceText || repair.translation.plainZh !== segment.translation.plainZh)) {
    issues.push("原文或白話稿與本次核對版本不同；保留本機修改，需重新核對後再作段落解釋。");
  }
  const text = segment.translation.plainZh;
  const usesComputationalThinking = paper.id === "paper-01" || paper.segments.some(s => /computational thinking\s*\(CT\)/i.test(s.sourceText));
  if (usesComputationalThinking && /CT\s*[（(]\s*(?:可能是)?(?:認知訓練|認知彈性)|(?:認知訓練|認知彈性|執行功能)\s*[（(]\s*CT|運算思維\s*[（(]\s*EF/i.test(text)) {
    issues.push("術語不一致：本篇 CT 是運算思維，EF 是執行功能；認知彈性是 EF 的構面。");
  }
  return issues;
}
