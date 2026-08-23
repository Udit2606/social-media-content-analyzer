import { Users } from "lucide-react";

import { SectionCard } from "@/components/common/section-card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { sentimentToPercent } from "@/lib/format";
import { SENTIMENT_BADGE, SENTIMENT_LABEL } from "@/lib/labels";
import type { AudienceInsight, SentimentAnalysis, ToneAnalysis } from "@/types/analysis";

interface ContentProfileCardProps {
  tone: ToneAnalysis;
  sentiment: SentimentAnalysis;
  audience: AudienceInsight;
}

/**
 * Tone, sentiment and audience in one card.
 *
 * These three answer the same question -- "who is this for and how does it
 * read?" -- so splitting them into three cards would fragment one thought
 * across a third of the screen. They are grouped rather than merged: each
 * still has its own labelled block.
 */
export function ContentProfileCard({
  tone,
  sentiment,
  audience,
}: ContentProfileCardProps) {
  const sentimentPercent = sentimentToPercent(sentiment.score);

  return (
    <SectionCard
      icon={Users}
      title="Tone, sentiment and audience"
      description="How the post reads, and who it appears to be written for."
    >
      <div className="space-y-5">
        <div className="space-y-2">
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Tone
          </p>
          <p className="text-sm font-medium">{tone.label}</p>
          {tone.descriptors.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {tone.descriptors.map((descriptor, index) => (
                <Badge key={`${descriptor}-${index}`} variant="secondary">
                  {descriptor}
                </Badge>
              ))}
            </div>
          )}
        </div>

        <Separator />

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
              Sentiment
            </p>
            <Badge variant={SENTIMENT_BADGE[sentiment.label]}>
              {SENTIMENT_LABEL[sentiment.label]}
            </Badge>
          </div>

          {/* Polarity shown on a negative-to-positive track rather than a bar,
              because the midpoint is neutral, not "bad". */}
          <div
            className="bg-secondary relative h-2 w-full rounded-full"
            role="img"
            aria-label={`Sentiment polarity: ${sentiment.score.toFixed(2)} on a scale from -1 negative to 1 positive`}
          >
            <div
              className="bg-foreground absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card transition-[left] duration-700"
              style={{ left: `${sentimentPercent}%` }}
            />
          </div>
          <div className="text-muted-foreground flex justify-between text-xs">
            <span>Negative</span>
            <span>Neutral</span>
            <span>Positive</span>
          </div>
        </div>

        <Separator />

        <div className="space-y-2">
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Audience
          </p>
          <p className="text-sm font-medium">{audience.primary}</p>
          <p className="text-muted-foreground text-sm">
            Reading level: {audience.readingLevel}
          </p>
          {audience.segments.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {audience.segments.map((segment, index) => (
                <Badge key={`${segment}-${index}`} variant="outline">
                  {segment}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>
    </SectionCard>
  );
}
