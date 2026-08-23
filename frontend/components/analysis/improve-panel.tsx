"use client";

import { Loader2, Sparkles, Wand2, XCircle } from "lucide-react";

import { RewriteCard } from "@/components/analysis/rewrite-card";
import { SectionCard } from "@/components/common/section-card";
import { ErrorState } from "@/components/states/error-state";
import { Button } from "@/components/ui/button";
import { PLATFORM_LABEL } from "@/lib/labels";
import type { AppError } from "@/lib/errors";
import type { ImprovedPost, Platform } from "@/types/analysis";

interface ImprovePanelProps {
  /**
   * Read-only here. The platform choice itself lives in `PlatformSelector`,
   * rendered once above both this panel and the optimization card so the two
   * can never disagree about which platform is selected.
   */
  platform: Platform;
  instruction: string;
  onInstructionChange: (instruction: string) => void;
  status: "idle" | "loading" | "done" | "error";
  improved: ImprovedPost | null;
  error: AppError | null;
  onImprove: () => void;
  onCancel: () => void;
}

/** Matches the backend's `instruction` cap in ImproveRequest. */
const INSTRUCTION_MAX_LENGTH = 500;

/**
 * The "Improve My Post" step: optionally steer a rewrite, then generate one
 * for the currently selected platform.
 *
 * Deliberately its own panel below the analysis rather than a modal or a new
 * page. The rewrite is only meaningful next to the weaknesses it is fixing, so
 * keeping both on screen lets the user check the fix against the problem.
 *
 * Its loading and error states are local: a failed rewrite must never blank
 * out the analysis the user already has.
 */
export function ImprovePanel({
  platform,
  instruction,
  onInstructionChange,
  status,
  improved,
  error,
  onImprove,
  onCancel,
}: ImprovePanelProps) {
  const isLoading = status === "loading";

  return (
    <div className="space-y-4">
      <SectionCard
        icon={Wand2}
        iconClassName="text-primary"
        title="Improve this post"
        description={`Generate a rewrite for ${PLATFORM_LABEL[platform]}, targeting the weaknesses above.`}
      >
        <div className="space-y-5">
          <div className="space-y-2">
            <label
              htmlFor="improve-instruction"
              className="text-muted-foreground text-xs font-medium tracking-wide uppercase"
            >
              Extra instruction{" "}
              <span className="text-muted-foreground/70 normal-case">(optional)</span>
            </label>
            <textarea
              id="improve-instruction"
              value={instruction}
              maxLength={INSTRUCTION_MAX_LENGTH}
              disabled={isLoading}
              onChange={(event) => onInstructionChange(event.target.value)}
              placeholder="e.g. Keep it under 100 words, or lead with the number."
              rows={2}
              className="border-input bg-background placeholder:text-muted-foreground focus-visible:ring-ring w-full resize-y rounded-lg border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none disabled:opacity-60"
            />
            <p className="text-muted-foreground text-right text-xs tabular-nums">
              {instruction.length}/{INSTRUCTION_MAX_LENGTH}
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            {isLoading && (
              <Button type="button" variant="outline" onClick={onCancel}>
                <XCircle aria-hidden="true" />
                Cancel
              </Button>
            )}
            <Button type="button" onClick={onImprove} disabled={isLoading}>
              {isLoading ? (
                <Loader2 className="animate-spin" aria-hidden="true" />
              ) : (
                <Sparkles aria-hidden="true" />
              )}
              {isLoading
                ? "Writing…"
                : status === "done"
                  ? "Regenerate"
                  : "Generate improved post"}
            </Button>
          </div>

          {isLoading && (
            <p role="status" aria-live="polite" className="text-muted-foreground text-sm">
              Rewriting for {PLATFORM_LABEL[platform]}…
            </p>
          )}
        </div>
      </SectionCard>

      {/*
        A failed rewrite is shown beside the analysis, not in place of it --
        the user keeps everything they already had.
      */}
      {status === "error" && error && (
        <ErrorState error={error} onRetry={onImprove} onReset={onCancel} />
      )}

      {status === "done" && improved && (
        <RewriteCard improved={improved} platform={platform} />
      )}
    </div>
  );
}
