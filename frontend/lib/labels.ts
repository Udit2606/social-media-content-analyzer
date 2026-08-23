import type {
  ExtractionMethod,
  Platform,
  ScoreBreakdown,
  SentimentLabel,
  Severity,
} from "@/types/analysis";
import type { ScoreTone } from "@/lib/format";

/**
 * Every user-facing label and colour mapping, in one file.
 *
 * Centralised so the UI never prints a raw API field name, and so wording or
 * colour can be changed in one edit instead of hunting through components.
 *
 * `BadgeTone` mirrors the Badge component's variants without importing from
 * `components/`, which keeps the dependency direction one-way: components may
 * depend on lib, never the reverse.
 */
export type BadgeTone =
  | "default"
  | "secondary"
  | "outline"
  | "success"
  | "warning"
  | "destructive";

/* ---------------------------------------------------------------- */
/* Scores                                                            */
/* ---------------------------------------------------------------- */

export const SCORE_LABELS: Record<
  keyof ScoreBreakdown,
  { label: string; help: string }
> = {
  hook: {
    label: "Hook",
    help: "How strongly the opening line stops the scroll.",
  },
  clarity: {
    label: "Clarity",
    help: "How easily a reader understands the post on first pass.",
  },
  callToAction: {
    label: "Call to action",
    help: "Whether the post asks the reader to do something.",
  },
  readability: {
    label: "Readability",
    help: "Sentence length, jargon and structure.",
  },
  emotionalAppeal: {
    label: "Emotional appeal",
    help: "How strongly the post evokes curiosity, excitement or urgency.",
  },
  audienceRelevance: {
    label: "Audience relevance",
    help: "How precisely the post speaks to a specific audience.",
  },
  hashtagQuality: {
    label: "Hashtag quality",
    help: "Relevance and usefulness of the hashtags used.",
  },
};

export const SCORE_TONE_LABEL: Record<ScoreTone, string> = {
  strong: "Strong",
  fair: "Needs work",
  weak: "Weak",
};

export const SCORE_TONE_BADGE: Record<ScoreTone, BadgeTone> = {
  strong: "success",
  fair: "warning",
  weak: "destructive",
};

/** Text colour utility per tone. Uses registered theme tokens, not raw vars. */
export const SCORE_TONE_TEXT: Record<ScoreTone, string> = {
  strong: "text-success",
  fair: "text-warning",
  weak: "text-destructive",
};

/** Fill colour utility per tone, for bars and the score ring. */
export const SCORE_TONE_FILL: Record<ScoreTone, string> = {
  strong: "bg-success",
  fair: "bg-warning",
  weak: "bg-destructive",
};

export const SCORE_TONE_STROKE: Record<ScoreTone, string> = {
  strong: "stroke-success",
  fair: "stroke-warning",
  weak: "stroke-destructive",
};

/* ---------------------------------------------------------------- */
/* Findings                                                          */
/* ---------------------------------------------------------------- */

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: "High impact",
  medium: "Medium impact",
  low: "Nice to have",
};

/** Sort weight, so the highest-impact item is always rendered first. */
export const SEVERITY_ORDER: Record<Severity, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

export const SEVERITY_BADGE: Record<Severity, BadgeTone> = {
  high: "destructive",
  medium: "warning",
  low: "secondary",
};

/* ---------------------------------------------------------------- */
/* Content profile                                                   */
/* ---------------------------------------------------------------- */

export const SENTIMENT_LABEL: Record<SentimentLabel, string> = {
  positive: "Positive",
  neutral: "Neutral",
  negative: "Negative",
  mixed: "Mixed",
};

export const SENTIMENT_BADGE: Record<SentimentLabel, BadgeTone> = {
  positive: "success",
  neutral: "secondary",
  negative: "destructive",
  mixed: "warning",
};

/* ---------------------------------------------------------------- */
/* Platforms and extraction                                          */
/* ---------------------------------------------------------------- */

export const PLATFORM_LABEL: Record<Platform, string> = {
  linkedin: "LinkedIn",
  instagram: "Instagram",
  x: "X",
  facebook: "Facebook",
};

/** Render order for the platform picker. Typed so a new Platform is a compile error. */
export const PLATFORM_ORDER: readonly Platform[] = [
  "linkedin",
  "instagram",
  "x",
  "facebook",
] as const;

/** One-line note on what the rewrite will optimise for on each platform. */
export const PLATFORM_HINT: Record<Platform, string> = {
  linkedin: "Professional tone, scannable paragraphs, 1-3 hashtags.",
  instagram: "Casual voice, hook-first, 5-15 hashtags.",
  x: "Terse and punchy, aiming to fit one post.",
  facebook: "Conversational storytelling, few or no hashtags.",
};

/** Explains to the user how the text was obtained, in plain language. */
export const EXTRACTION_METHOD_LABEL: Record<ExtractionMethod, string> = {
  pdf_text: "Read directly from the PDF",
  ocr_image: "Read from the image using OCR",
  ocr_pdf_fallback: "Scanned PDF, read using OCR",
};
