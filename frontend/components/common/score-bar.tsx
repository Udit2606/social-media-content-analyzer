import { Progress } from "@/components/ui/progress";
import { clampScore, getScoreTone } from "@/lib/format";
import { SCORE_TONE_FILL } from "@/lib/labels";

interface ScoreBarProps {
  label: string;
  value: number;
  /** Short explanation of what this score measures. */
  help?: string;
}

/**
 * One labelled 0-100 bar.
 *
 * Extracted so the hook / clarity / CTA bars cannot drift apart in spacing,
 * colour thresholds or accessible naming. The colour comes from the shared
 * getScoreTone(), so a bar can never disagree with the score ring above it.
 */
export function ScoreBar({ label, value, help }: ScoreBarProps) {
  const score = clampScore(value);

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-muted-foreground text-xs tabular-nums">{score}/100</span>
      </div>

      <Progress
        value={score}
        aria-label={`${label}: ${score} out of 100`}
        indicatorClassName={SCORE_TONE_FILL[getScoreTone(score)]}
      />

      {help && <p className="text-muted-foreground text-xs">{help}</p>}
    </div>
  );
}
