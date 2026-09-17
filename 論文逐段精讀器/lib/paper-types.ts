export type ReviewStatus =
  | "auto-generated"
  | "needs-review"
  | "reviewed"
  | "published";

export interface SegmentFragment {
  page: number;
  bbox: [number, number, number, number];
  pageSize: [number, number];
}

export interface TranslationDraft {
  faithfulZh: string;
  plainZh: string;
  status: "untranslated" | "ai-draft" | "reviewed";
  reviewedAt: string | null;
  generatedAt?: string;
  generatedBy?: string;
}

export interface PaperExhibit {
  id: string;
  label: string;
  kind: "figure" | "table";
  number: string;
  page: number;
  caption: string;
  captionZh: string;
  bbox: [number, number, number, number];
  pageSize: [number, number];
  imageUrl: string;
  extractionStatus: "ok" | "manual-crop";
  extractionMethod: string;
  captionSegmentId: string | null;
  explanationSegmentIds: string[];
}

export interface ReferenceAbstract {
  status: "available" | "not-found" | "not-checked";
  originalText: string;
  summaryZh: string;
  faithfulZh?: string;
  translationSourceSha256?: string;
  translationStatus?: "ai-draft";
  summaryMethod?: "model-summary" | "extractive-translation" | "source-grounded" | null;
  sourceUrl: string | null;
  sourceType: "crossref" | "publisher" | "author" | "openalex" | "semantic-scholar" | "europe-pmc" | "eric" | "openaire" | "doaj" | "ebsco" | null;
  abstractOrigin?: string;
  retrievalReason?: string;
  checkedAt: string | null;
}

export interface PaperReference {
  id: string;
  label: string;
  authors: string;
  firstAuthor: string;
  year: string;
  title: string;
  sourceText: string;
  fragments: SegmentFragment[];
  doi: string | null;
  printedDoi?: string | null;
  doiResolution?: { method: "title-author-year"; sourceUrl: string; checkedAt: string };
  extractionStatus: "needs-review" | "reviewed";
  identityStatus: "not-checked" | "verified" | "title-mismatch";
  abstract: ReferenceAbstract;
}

export interface PaperCitation {
  id: string;
  segmentId: string;
  label: string;
  sourceContext: string;
  referenceIds: string[];
  matchStatus: "matched" | "ambiguous";
  relationshipZh?: string;
}

export interface PaperSegment {
  id: string;
  order: number;
  section: string;
  kind: "heading" | "body" | "caption";
  sourceText: string;
  fragments: SegmentFragment[];
  translation: TranslationDraft;
  reviewStatus: ReviewStatus;
  confidence: number;
  excluded?: boolean;
  readingRole?: "statement" | "appendix";
  paragraphAssessment?: {
    status: "fragment" | "needs-review";
    reasons: string[];
    relatedSegmentIds: string[];
    sourceTextSha256: string;
  };
  exhibitIds?: string[];
  exhibitMentions?: { exhibitId: string; label: string; page: number; bbox: [number, number, number, number] }[];
  mergedIntoSegmentId?: string;
}

export interface PaperDocument {
  schemaVersion: string;
  id: string;
  number: number;
  title: string;
  year: number | null;
  sourceFileName: string;
  sourceSha256: string;
  pdfUrl: string;
  pageCount: number;
  language: "en";
  readerLanguage: "zh-Hant";
  publicationStatus: "draft" | "reviewed" | "published";
  generatedAt: string;
  segments: PaperSegment[];
  readingOrderRepair?: { revision: string; previousSegmentIds: string[] };
  inlineExhibitsEnabled?: boolean;
  readingUnitRepairs?: { revision: string; targetId: string; absorbedIds: string[]; previousSegments: PaperSegment[] }[];
  pendingReadingUnitRepairs?: string[];
  exhibits?: PaperExhibit[];
  references?: PaperReference[];
  citations?: PaperCitation[];
  exhibitCompanion?: {
    revision: string;
    links: ExhibitCompanionLink[];
    studies: Record<string, ExhibitStudy>;
  };
  readingQuality?: {
    revision: string;
    explanationRepairs: { segmentId: string; sourceText: string; previousTranslation: TranslationDraft; translation: TranslationDraft }[];
    appendices: { exhibit: PaperExhibit; relatedSegmentIds: string[]; faithfulZh: string; guideZh: string[] }[];
  };
}

export interface ExhibitCompanionLink {
  segmentId: string;
  exhibitId: string;
  method: "explicit" | "semantic";
  confidence: "high" | "candidate";
  relationshipZh: string;
  evidenceQuote: string;
  sourceSegmentIds: string[];
  sourceTextSha256: string;
}

export interface ExhibitStudy {
  summaryZh: string;
  guideZh: string[];
  limitsZh: string[];
  sourceSegmentIds: string[];
  status: "ai-draft";
}

export interface PaperSummary {
  id: string;
  number: number;
  title: string;
  year: number | null;
  pageCount: number;
  segmentCount: number;
  includedSegmentCount?: number;
  bodySegmentCount?: number;
  publicationStatus: "draft" | "reviewed" | "published";
  dataUrl: string;
  pdfUrl: string;
  sourceSha256: string;
}

export interface PaperManifest {
  schemaVersion: string;
  generatedAt: string;
  paperCount: number;
  papers: PaperSummary[];
}

export interface ReaderPaperState {
  version: 1;
  paperId: string;
  sourceSha256: string;
  currentSegmentId: string | null;
  seen: string[];
  understood: string[];
  bookmarks: string[];
  notes: Record<string, string>;
  dimOpacity: number;
  reducedMotion: boolean;
  highContrast: boolean;
  updatedAt: string;
}
