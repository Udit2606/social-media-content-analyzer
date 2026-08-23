import { BarChart3 } from "lucide-react";

import { SectionCard } from "@/components/common/section-card";
import { Badge } from "@/components/ui/badge";
import { formatReadingTime, getScoreTone } from "@/lib/format";
import { SCORE_TONE_BADGE } from "@/lib/labels";
import type { ContentMetrics } from "@/types/analysis";

interface MetricsCardProps {
  metrics: ContentMetrics;
}

/**
 * Deterministic content statistics: word/character/sentence counts, average
 * sentence length, reading time, and Flesch Reading Ease readability.
 *
 * Everything on this card is arithmetic done directly on the text -- see
 * `ContentMetrics` in types/analysis.ts for why that matters and how it
 * differs from the AI-judged "Readability" bar inside the Engagement score
 * card above. The description line says so explicitly, since the two
 * numbers can legitimately disagree and a user comparing them deserves to
 * know that's expected, not a bug.
 */
export function MetricsCard({ metrics }: MetricsCardProps) {
  const tone = getScoreTone(metrics.readabilityScore);

  const stats = [
    { label: "Words", value: metrics.wordCount },
    { label: "Characters", value: metrics.characterCount },
    { label: "Sentences", value: metrics.sentenceCount },
    { label: "Avg words / sentence", value: metrics.avgWordsPerSentence.toFixed(1) },
    { label: "Reading time", value: formatReadingTime(metrics.readingTimeSeconds) },
  ];

  return (
    <SectionCard
      icon={BarChart3}
      title="Content metrics"
      description="Deterministic text statistics -- calculated directly from the text, not by AI."
      meta={<Badge variant={SCORE_TONE_BADGE[tone]}>{metrics.readabilityLevel}</Badge>}
    >
      <dl className="grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-5">
        {stats.map((stat) => (
          <div key={stat.label}>
            <dt className="text-muted-foreground text-xs">{stat.label}</dt>
            <dd className="text-lg font-semibold tabular-nums">{stat.value}</dd>
          </div>
        ))}
      </dl>

      <p className="text-muted-foreground mt-4 text-xs">
        Flesch Reading Ease score: {metrics.readabilityScore.toFixed(1)}/100. This is a
        different number from the "Readability" bar above -- that one is the AI's
        holistic judgement; this one is a formula based on sentence and syllable length.
      </p>
    </SectionCard>
  );
}
