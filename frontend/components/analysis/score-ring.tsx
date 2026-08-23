"use client";

import { useEffect, useState } from "react";

import { clampScore, getScoreTone } from "@/lib/format";
import { SCORE_TONE_STROKE, SCORE_TONE_TEXT } from "@/lib/labels";
import { cn } from "@/lib/utils";

interface ScoreRingProps {
  score: number;
  className?: string;
}

/**
 * The headline 0-100 score, drawn as an animated circular gauge.
 *
 * Hand-built with SVG rather than a charting library: it is about twenty lines,
 * and a chart dependency for one circle would be dead weight in the bundle.
 *
 * The ring scales with its container via viewBox rather than a fixed pixel
 * size, so it shrinks on small screens instead of crowding the bars beside it.
 */
export function ScoreRing({ score, className }: ScoreRingProps) {
  const value = clampScore(score);
  const tone = getScoreTone(value);
  const [displayed, setDisplayed] = useState(0);

  // Animate up from zero on mount so the ring sweeps into place.
  useEffect(() => {
    const frame = requestAnimationFrame(() => setDisplayed(value));
    return () => cancelAnimationFrame(frame);
  }, [value]);

  const RADIUS = 69;
  const circumference = 2 * Math.PI * RADIUS;
  const offset = circumference - (displayed / 100) * circumference;

  return (
    <div
      className={cn("relative w-32 shrink-0 sm:w-36", className)}
      role="img"
      aria-label={`Overall engagement score: ${value} out of 100`}
    >
      <svg viewBox="0 0 148 148" className="w-full -rotate-90">
        <circle
          cx="74"
          cy="74"
          r={RADIUS}
          fill="none"
          strokeWidth="10"
          className="stroke-secondary"
        />
        <circle
          cx="74"
          cy="74"
          r={RADIUS}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className={cn(
            "transition-[stroke-dashoffset] duration-1000 ease-out",
            SCORE_TONE_STROKE[tone],
          )}
        />
      </svg>

      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn("text-4xl font-semibold tabular-nums", SCORE_TONE_TEXT[tone])}>
          {value}
        </span>
        <span className="text-muted-foreground text-xs">out of 100</span>
      </div>
    </div>
  );
}
