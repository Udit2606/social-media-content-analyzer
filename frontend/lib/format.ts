/**
 * Pure formatting helpers. No React, no domain vocabulary, no side effects.
 *
 * Display *labels* live in `lib/labels.ts`; this file only transforms values.
 */

/** 1536 -> "1.5 KB". Used in the file preview and size-limit errors. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unitIndex]}`;
}

/** Clamp any number the backend sends into the 0-100 range the UI assumes. */
export function clampScore(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

export type ScoreTone = "strong" | "fair" | "weak";

/**
 * The single place that decides what a score "means".
 *
 * Every score colour and label in the UI derives from this, so the ring, the
 * badges and the bars can never drift apart on where "good" starts.
 */
export function getScoreTone(score: number): ScoreTone {
  if (score >= 75) return "strong";
  if (score >= 50) return "fair";
  return "weak";
}

/** -1..1 polarity -> a 0-100 position for rendering on a track. */
export function sentimentToPercent(score: number): number {
  if (!Number.isFinite(score)) return 50;
  return Math.round(((Math.max(-1, Math.min(1, score)) + 1) / 2) * 100);
}

/** 42 -> "< 1 min read"; 185 -> "3 min read". Backend sends raw seconds. */
export function formatReadingTime(seconds: number): string {
  if (seconds < 60) return "< 1 min read";
  const minutes = Math.round(seconds / 60);
  return `${minutes} min read`;
}
