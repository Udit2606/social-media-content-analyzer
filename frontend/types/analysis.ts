/**
 * The contract between this frontend and the FastAPI backend.
 *
 * These types mirror the Pydantic models in `backend/app/schemas/analysis.py`
 * exactly. The backend serialises snake_case Python fields to camelCase on the
 * wire via an alias generator, so every field name here is the camelCase form.
 *
 * This file is the single source of truth for response shapes. Nothing else in
 * the app is allowed to invent its own idea of what the backend returns, and no
 * component reads an untyped field.
 *
 * Three endpoints, three response shapes:
 *   POST /api/upload        -> UploadResponse   (extraction only)
 *   POST /api/analyze-text  -> AnalyzeTextResponse (AI analysis only)
 *   POST /api/improve       -> ImproveResponse  (AI rewrite)
 */

/* ------------------------------------------------------------------ */
/* Extraction                                                          */
/* ------------------------------------------------------------------ */

/** How the text was obtained from the uploaded file. */
export type ExtractionMethod = "pdf_text" | "ocr_image" | "ocr_pdf_fallback";

export type FileKind = "pdf" | "image";

export interface FileInfo {
  name: string;
  kind: FileKind;
  sizeBytes: number;
  mimeType: string;
}

export interface ExtractionResult {
  method: ExtractionMethod;
  /** The extracted text, with paragraph breaks preserved. */
  text: string;
  /** Null for images, which have no pages. */
  pageCount: number | null;
  wordCount: number;
  characterCount: number;
  /** 0-100 for OCR results, null when the text came from a digital PDF. */
  confidence: number | null;
}

export interface ProcessingInfo {
  durationMs: number;
  engine: string;
  /** Plain-language note on how the text was obtained. */
  notes: string;
}

/** Success body of POST /api/upload. */
export interface UploadResponse {
  success: true;
  file: FileInfo;
  extraction: ExtractionResult;
  processing: ProcessingInfo;
}

/* ------------------------------------------------------------------ */
/* Scoring                                                             */
/* ------------------------------------------------------------------ */

/**
 * The seven sub-scores behind the headline number, each 0-100.
 *
 * Every key here is rendered, so adding one is a contract change on both
 * sides rather than an optional extra.
 */
export interface ScoreBreakdown {
  /** How strongly the opening line stops the scroll. */
  hook: number;
  /** How easily a reader understands the post on first pass. */
  clarity: number;
  /** Whether the post asks the reader to do something. */
  callToAction: number;
  /** Sentence length, jargon, structure. */
  readability: number;
  /** Curiosity, excitement, pride, urgency. */
  emotionalAppeal: number;
  /** How precisely the post speaks to a specific audience. */
  audienceRelevance: number;
  /** Relevance and usefulness of the hashtags used. */
  hashtagQuality: number;
}

/* ------------------------------------------------------------------ */
/* Content profile                                                     */
/* ------------------------------------------------------------------ */

export type SentimentLabel = "positive" | "neutral" | "negative" | "mixed";

export interface ToneAnalysis {
  /** Short human summary, e.g. "Confident and informative". */
  label: string;
  /** Individual descriptors, e.g. ["confident", "technical"]. */
  descriptors: string[];
}

export interface SentimentAnalysis {
  label: SentimentLabel;
  /** Polarity from -1 (very negative) to 1 (very positive). */
  score: number;
}

export interface AudienceInsight {
  /** Who this post appears to be written for. */
  primary: string;
  /** Narrower segments within that audience. */
  segments: string[];
  /** e.g. "Professional / technical". */
  readingLevel: string;
}

/* ------------------------------------------------------------------ */
/* Findings                                                            */
/* ------------------------------------------------------------------ */

export type Severity = "high" | "medium" | "low";

/**
 * Shared shape for strengths, weaknesses and suggestions.
 *
 * They render identically apart from icon and colour, so they share one type
 * and one list component instead of three near-duplicates.
 */
export interface Finding {
  id: string;
  title: string;
  detail: string;
}

export type Strength = Finding;

export interface Weakness extends Finding {
  severity: Severity;
}

export interface Suggestion extends Finding {
  severity: Severity;
  /** Optional concrete rewrite of the offending line. */
  example?: string | null;
}

/* ------------------------------------------------------------------ */
/* Analysis                                                            */
/* ------------------------------------------------------------------ */

/**
 * Deterministic text statistics -- computed by the backend with plain
 * arithmetic and the Flesch Reading Ease formula, never by the AI model. The
 * same input text always produces the same `metrics`, which is not true of
 * any other field on `ContentAnalysis`.
 *
 * Note there are two different "readability" numbers in this app:
 * `ScoreBreakdown.readability` is the AI's holistic judgement (jargon,
 * structure, tone); `ContentMetrics.readabilityScore` is this formula-based
 * score. They can legitimately disagree -- one is a semantic opinion, the
 * other is arithmetic on sentence and syllable counts.
 */
export interface ContentMetrics {
  characterCount: number;
  wordCount: number;
  sentenceCount: number;
  avgWordsPerSentence: number;
  readingTimeSeconds: number;
  /** Flesch Reading Ease, 0-100. Higher means easier to read. */
  readabilityScore: number;
  /** Short label bucketed from readabilityScore, e.g. "Easy to read". */
  readabilityLevel: string;
}

export interface ContentAnalysis {
  overallScore: number;
  scores: ScoreBreakdown;
  tone: ToneAnalysis;
  sentiment: SentimentAnalysis;
  audience: AudienceInsight;
  strengths: Strength[];
  weaknesses: Weakness[];
  suggestions: Suggestion[];
  metrics: ContentMetrics;
}

/** Success body of POST /api/analyze-text. */
export interface AnalyzeTextResponse {
  success: true;
  analysis: ContentAnalysis;
}

/* ------------------------------------------------------------------ */
/* Improve My Post                                                     */
/* ------------------------------------------------------------------ */

/**
 * The platforms the backend accepts. Matches the `Platform` Literal in
 * `backend/app/schemas/analysis.py` -- note it is "x", not "twitter", and
 * there is no "general".
 */
export type Platform = "linkedin" | "instagram" | "x" | "facebook";

export interface ImprovedPost {
  hook: string;
  body: string;
  cta: string;
  /** Suggested hashtags, without the leading "#". */
  hashtags: string[];
  /** The complete, ready-to-publish post. */
  fullPost: string;
}

/** Success body of POST /api/improve. */
export interface ImproveResponse {
  success: true;
  platform: Platform;
  improved: ImprovedPost;
}

/* ------------------------------------------------------------------ */
/* Platform-specific optimization                                      */
/* ------------------------------------------------------------------ */

/**
 * How one post should be shaped for one platform.
 *
 * A second, independent analysis dimension from `ContentAnalysis` above --
 * that one is platform-agnostic; this judges the same text against ONE named
 * platform's norms, and the answer legitimately differs per platform for
 * identical input. `engagementScore` here is a platform-FIT score, not a
 * restatement of `ContentAnalysis.overallScore`.
 */
export interface PlatformOptimization {
  engagementScore: number;
  recommendedTone: string;
  recommendedLength: string;
  hookRecommendation: string;
  ctaRecommendation: string;
  /** Without the leading "#", matching `ImprovedPost.hashtags`. */
  hashtagRecommendation: string[];
}

/** Success body of POST /api/platform-analysis. */
export interface PlatformAnalysisResponse {
  success: true;
  platform: Platform;
  optimization: PlatformOptimization;
}

/* ------------------------------------------------------------------ */
/* Errors                                                              */
/* ------------------------------------------------------------------ */

/** Failure body, identical across every endpoint. */
export interface ApiErrorBody {
  success: false;
  error: {
    code: string;
    message: string;
    hint?: string;
  };
}
