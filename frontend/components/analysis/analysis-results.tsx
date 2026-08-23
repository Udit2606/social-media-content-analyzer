import { CheckCircle2, Loader2 } from "lucide-react";

import { ContentProfileCard } from "@/components/analysis/content-profile-card";
import { EngagementScoreCard } from "@/components/analysis/engagement-score-card";
import { ExtractedTextCard } from "@/components/analysis/extracted-text-card";
import {
  StrengthsCard,
  SuggestionsCard,
  WeaknessesCard,
} from "@/components/analysis/findings-cards";
import { MetricsCard } from "@/components/analysis/metrics-card";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ContentAnalysis, UploadResponse } from "@/types/analysis";

interface AnalysisResultsProps {
  upload: UploadResponse;
  /** Null while the AI call is still in flight; the extracted text shows anyway. */
  analysis: ContentAnalysis | null;
  isAnalyzing: boolean;
}

/**
 * Composes the result sections into one responsive layout.
 *
 * Layout only: no state, no fetching, no decisions beyond ordering and grid
 * placement. Keeping composition separate from the cards means the page can be
 * rearranged without touching a single card.
 *
 * This component renders a PARTIAL state on purpose. Extraction and analysis
 * are two separate requests, so there is a real window where the text exists
 * and the analysis does not. Rather than hiding everything behind one spinner,
 * the text is shown immediately and the analysis area holds skeletons until it
 * arrives -- which is where most of the perceived speed comes from.
 *
 * Order: extracted text plus its deterministic metrics (proof of what was
 * read, and objective facts about it), then the AI verdict, then the
 * reasoning behind it. The metrics card only joins the text once `analysis`
 * exists -- the backend computes them as part of that same response, not
 * as part of extraction, so there is nothing to show for them any earlier.
 */
export function AnalysisResults({
  upload,
  analysis,
  isAnalyzing,
}: AnalysisResultsProps) {
  return (
    <div className="space-y-4">
      {/*
        tabIndex={-1} makes this programmatically focusable so the parent can
        move focus here when results arrive, which is how a keyboard or
        screen-reader user learns the page changed.
      */}
      <div
        id="analysis-results"
        tabIndex={-1}
        className="animate-fade-up flex items-center gap-2 outline-none"
        role="status"
        aria-live="polite"
      >
        {analysis ? (
          <>
            <CheckCircle2 className="text-success size-4 shrink-0" aria-hidden="true" />
            <h2 className="text-sm font-medium">
              Analysis complete for{" "}
              <span className="text-muted-foreground font-normal">
                {upload.file.name}
              </span>
            </h2>
          </>
        ) : (
          <>
            <Loader2 className="text-primary size-4 shrink-0 animate-spin" aria-hidden="true" />
            <h2 className="text-sm font-medium">
              Text extracted. Analysing engagement…
            </h2>
          </>
        )}
      </div>

      {analysis ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <ExtractedTextCard extraction={upload.extraction} />
          <MetricsCard metrics={analysis.metrics} />
        </div>
      ) : (
        <ExtractedTextCard extraction={upload.extraction} />
      )}

      {analysis ? (
        <>
          <EngagementScoreCard
            overallScore={analysis.overallScore}
            scores={analysis.scores}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <ContentProfileCard
              tone={analysis.tone}
              sentiment={analysis.sentiment}
              audience={analysis.audience}
            />
            <StrengthsCard strengths={analysis.strengths} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <WeaknessesCard weaknesses={analysis.weaknesses} />
            <SuggestionsCard suggestions={analysis.suggestions} />
          </div>
        </>
      ) : (
        isAnalyzing && <AnalysisSkeleton />
      )}
    </div>
  );
}

/**
 * Placeholder matching the real analysis layout, so nothing jumps when the
 * data lands. Hidden from assistive tech: it carries no information, and the
 * status message above already announces what is happening.
 */
function AnalysisSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-4">
      <Card>
        <CardContent className="grid gap-8 pt-5 sm:grid-cols-[auto_1fr] sm:items-center sm:pt-6">
          <Skeleton className="mx-auto size-36 rounded-full" />
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="space-y-2">
                <Skeleton className="h-3 w-28" />
                <Skeleton className="h-2 w-full" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 2 }).map((_, card) => (
          <Card key={card}>
            <CardContent className="space-y-3 pt-5 sm:pt-6">
              <Skeleton className="h-4 w-1/3" />
              {Array.from({ length: 4 }).map((_, row) => (
                <Skeleton key={row} className="h-3" style={{ width: `${92 - row * 11}%` }} />
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
