"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { Info, Sparkles } from "lucide-react";

import { AnalysisResults } from "@/components/analysis/analysis-results";
import { ImprovePanel } from "@/components/analysis/improve-panel";
import { PlatformOptimizationCard } from "@/components/analysis/platform-optimization-card";
import { PlatformSelector } from "@/components/analysis/platform-selector";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";
import { FilePreview } from "@/components/upload/file-preview";
import { UploadZone } from "@/components/upload/upload-zone";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAnalyzer } from "@/hooks/use-analyzer";

interface AnalyzerProps {
  /**
   * Rendered only in the empty state. Lets the page pass server-rendered
   * marketing content that disappears once the user is working, without the
   * page itself needing to be a Client Component.
   */
  emptyStateSlot?: ReactNode;
}

/**
 * The one stateful component in the app, and the only client boundary that
 * matters.
 *
 * Everything above it -- page, header, footer, hero -- stays a Server
 * Component and ships zero JavaScript. Everything below it is presentational
 * and receives data through props. Its single job is to read the current
 * phase from useAnalyzer and decide which screen to show.
 */
export function Analyzer({ emptyStateSlot }: AnalyzerProps) {
  const {
    phase,
    file,
    upload,
    analysis,
    error,
    notice,
    isRunning,
    platform,
    selectPlatform,
    platformOptStatus,
    platformOptimization,
    platformOptError,
    retryPlatformOptimization,
    improveStatus,
    improved,
    improveError,
    isImproving,
    instruction,
    setInstruction,
    selectFile,
    rejectFile,
    analyze,
    improve,
    cancelRun,
    cancelImprove,
    reset,
  } = useAnalyzer();

  const resultsRef = useRef<HTMLDivElement>(null);

  /**
   * Results render well below the fold. Without this, a click on Analyse looks
   * like nothing happened. Scrolling brings them into view for sighted users;
   * moving focus tells keyboard and screen-reader users that new content
   * exists and puts them at the top of it.
   *
   * Keyed on the arrival of the extracted text rather than on completion, so
   * the jump happens as soon as there is something worth reading.
   */
  const hasExtraction = Boolean(upload);
  useEffect(() => {
    if (!hasExtraction) return;
    const heading = resultsRef.current?.querySelector<HTMLElement>("#analysis-results");
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    heading?.focus({ preventScroll: true });
  }, [hasExtraction]);

  // In the error state the retry lives inside ErrorState, so the card's own
  // submit button is hidden to avoid two controls doing the same thing.
  const showSubmitButton = phase === "selected" || phase === "complete";

  // Only the very first wait gets the full-screen loading card. Once the text
  // exists, AnalysisResults shows it alongside its own inline skeletons, which
  // is far more useful than a spinner covering everything.
  const showFullLoadingCard = phase === "extracting";

  return (
    <section className="space-y-4" aria-label="Content analyzer">
      <Card>
        <CardContent className="space-y-4 pt-5 sm:pt-6">
          {file ? (
            <>
              <FilePreview file={file} disabled={isRunning} onRemove={reset} />

              {notice && (
                <Alert variant="info">
                  <Info aria-hidden="true" />
                  <AlertDescription>{notice}</AlertDescription>
                </Alert>
              )}

              {showSubmitButton && (
                <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
                  <Button variant="outline" onClick={reset} disabled={isImproving}>
                    Choose another file
                  </Button>
                  {/*
                    `disabled` is a UX affordance, not the real guard -- a
                    double click can land two events before React re-renders,
                    so useAnalyzer refuses a second run internally too.
                  */}
                  <Button onClick={analyze} disabled={isRunning}>
                    <Sparkles aria-hidden="true" />
                    {phase === "complete" ? "Re-run analysis" : "Analyse content"}
                  </Button>
                </div>
              )}
            </>
          ) : (
            <UploadZone
              disabled={isRunning}
              onFilesSelected={selectFile}
              onReject={rejectFile}
            />
          )}
        </CardContent>
      </Card>

      {phase === "idle" && emptyStateSlot}

      {showFullLoadingCard && <LoadingState onCancel={cancelRun} />}

      {/*
        Extraction may have succeeded before the failure, so this renders
        alongside whatever results already exist rather than replacing them.
      */}
      {phase === "error" && error && (
        <ErrorState error={error} onRetry={file ? analyze : undefined} onReset={reset} />
      )}

      {upload && (
        <div ref={resultsRef} className="scroll-mt-20 space-y-4">
          <AnalysisResults
            upload={upload}
            analysis={analysis}
            isAnalyzing={phase === "analyzing"}
          />

          {/*
            Platform-specific optimization and the rewrite both depend on the
            general analysis existing, and both read the SAME platform
            selection -- rendered once here, above both, so they can never
            show mismatched platforms.
          */}
          {analysis && (
            <Card>
              <CardContent className="pt-5 sm:pt-6">
                <PlatformSelector
                  platform={platform}
                  onChange={selectPlatform}
                  disabled={isImproving}
                />
              </CardContent>
            </Card>
          )}

          {analysis && (
            <PlatformOptimizationCard
              platform={platform}
              status={platformOptStatus}
              optimization={platformOptimization}
              error={platformOptError}
              onRetry={retryPlatformOptimization}
            />
          )}

          {analysis && (
            <ImprovePanel
              platform={platform}
              instruction={instruction}
              onInstructionChange={setInstruction}
              status={improveStatus}
              improved={improved}
              error={improveError}
              onImprove={improve}
              onCancel={cancelImprove}
            />
          )}
        </div>
      )}
    </section>
  );
}
