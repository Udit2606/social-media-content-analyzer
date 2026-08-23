"use client";

import { Hash, Loader2, MousePointerClick, Ruler, Sparkles, Target } from "lucide-react";

import { SectionCard } from "@/components/common/section-card";
import { ErrorState } from "@/components/states/error-state";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { clampScore, getScoreTone } from "@/lib/format";
import { PLATFORM_LABEL, SCORE_TONE_BADGE } from "@/lib/labels";
import type { AppError } from "@/lib/errors";
import type { Platform, PlatformOptimization } from "@/types/analysis";

interface PlatformOptimizationCardProps {
  platform: Platform;
  status: "idle" | "loading" | "done" | "error";
  optimization: PlatformOptimization | null;
  error: AppError | null;
  onRetry: () => void;
}

/**
 * Platform, engagement score, and the four concrete recommendations, from
 * POST /api/platform-analysis.
 *
 * This is a platform-FIT score, not the general engagement score shown
 * higher on the page -- the same post can score well here for LinkedIn and
 * poorly for X, which is the entire point of the feature. The heading always
 * names the platform explicitly so the two scores are never confused for
 * one another.
 *
 * Fetches automatically when the platform selection changes (see
 * useAnalyzer), so this card's job is purely to render whichever status it
 * is hands: loading, error, or the result. It never triggers a fetch itself.
 */
export function PlatformOptimizationCard({
  platform,
  status,
  optimization,
  error,
  onRetry,
}: PlatformOptimizationCardProps) {
  if (status === "error" && error) {
    return <ErrorState error={error} onRetry={onRetry} onReset={onRetry} />;
  }

  if (status === "loading" || !optimization) {
    return (
      <SectionCard
        icon={Target}
        iconClassName="text-primary"
        title={`Optimizing for ${PLATFORM_LABEL[platform]}`}
        description="Scoring this post against the platform's own norms."
      >
        <div role="status" aria-live="polite" className="space-y-4">
          <span className="sr-only">Loading {PLATFORM_LABEL[platform]} recommendations…</span>
          <div className="flex items-center gap-3">
            <Loader2 className="text-primary size-4 animate-spin" aria-hidden="true" />
            <Skeleton className="h-4 w-32" />
          </div>
          <div className="space-y-2" aria-hidden="true">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
            <Skeleton className="h-3 w-3/5" />
          </div>
        </div>
      </SectionCard>
    );
  }

  const score = clampScore(optimization.engagementScore);
  const tone = getScoreTone(score);

  return (
    <SectionCard
      icon={Target}
      iconClassName="text-primary"
      title={`${PLATFORM_LABEL[platform]} fit`}
      description="How this post scores against this platform's own norms, and what to adjust."
      meta={
        <Badge variant={SCORE_TONE_BADGE[tone]}>Engagement score: {score}/100</Badge>
      }
    >
      <div className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
              <Sparkles className="size-3.5" aria-hidden="true" />
              Recommended tone
            </p>
            <p className="text-sm">{optimization.recommendedTone}</p>
          </div>

          <div className="space-y-1">
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
              <Ruler className="size-3.5" aria-hidden="true" />
              Recommended length
            </p>
            <p className="text-sm">{optimization.recommendedLength}</p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="space-y-1">
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
              <Target className="size-3.5" aria-hidden="true" />
              Hook recommendation
            </p>
            <p className="text-sm leading-relaxed">{optimization.hookRecommendation}</p>
          </div>

          <div className="space-y-1">
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
              <MousePointerClick className="size-3.5" aria-hidden="true" />
              Call to action recommendation
            </p>
            <p className="text-sm leading-relaxed">{optimization.ctaRecommendation}</p>
          </div>
        </div>

        {optimization.hashtagRecommendation.length > 0 && (
          <div className="space-y-2">
            <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-wide uppercase">
              <Hash className="size-3.5" aria-hidden="true" />
              Hashtag recommendation
            </p>
            <div className="flex flex-wrap gap-2">
              {optimization.hashtagRecommendation.map((tag, index) => (
                <Badge key={`${tag}-${index}`} variant="secondary">
                  #{tag}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </div>
    </SectionCard>
  );
}
