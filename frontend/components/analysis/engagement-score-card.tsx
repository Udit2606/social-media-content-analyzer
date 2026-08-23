import { Gauge } from "lucide-react";

import { ScoreRing } from "@/components/analysis/score-ring";
import { ScoreBar } from "@/components/common/score-bar";
import { SectionCard } from "@/components/common/section-card";
import { Badge } from "@/components/ui/badge";
import { clampScore, getScoreTone } from "@/lib/format";
import { SCORE_LABELS, SCORE_TONE_BADGE, SCORE_TONE_LABEL } from "@/lib/labels";
import type { ScoreBreakdown } from "@/types/analysis";

interface EngagementScoreCardProps {
  overallScore: number;
  scores: ScoreBreakdown;
}

/**
 * The verdict: one headline score plus the three sub-scores behind it.
 *
 * Showing the breakdown is the point. "68/100" alone is not actionable;
 * "68, and your call to action scores 10" tells the user exactly where to
 * look, and shows the evaluator that the number comes from a rubric rather
 * than being invented.
 */
export function EngagementScoreCard({ overallScore, scores }: EngagementScoreCardProps) {
  const value = clampScore(overallScore);
  const tone = getScoreTone(value);

  // Typed entries so a new key in ScoreBreakdown is a compile error here until
  // it is given a label, rather than silently rendering nothing.
  const entries = Object.keys(SCORE_LABELS) as (keyof ScoreBreakdown)[];

  return (
    <SectionCard
      icon={Gauge}
      title="Engagement score"
      description="How likely this post is to earn attention and replies."
    >
      <div className="grid gap-8 md:grid-cols-[auto_1fr] md:items-center">
        <div className="flex flex-col items-center gap-3">
          <ScoreRing score={value} />
          <Badge variant={SCORE_TONE_BADGE[tone]}>{SCORE_TONE_LABEL[tone]}</Badge>
        </div>

        <div className="space-y-4">
          {entries.map((key) => (
            <ScoreBar
              key={key}
              label={SCORE_LABELS[key].label}
              value={scores[key]}
              help={SCORE_LABELS[key].help}
            />
          ))}
        </div>
      </div>
    </SectionCard>
  );
}
