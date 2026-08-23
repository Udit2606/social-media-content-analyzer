import { AlertTriangle, FileSearch } from "lucide-react";

import { CopyButton } from "@/components/common/copy-button";
import { SectionCard } from "@/components/common/section-card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { EXTRACTION_METHOD_LABEL } from "@/lib/labels";
import type { ExtractionResult } from "@/types/analysis";

interface ExtractedTextCardProps {
  extraction: ExtractionResult;
}

/** Below this, OCR output is unreliable enough that the user should be warned. */
const LOW_CONFIDENCE_THRESHOLD = 75;

/**
 * The raw text the analysis was performed on.
 *
 * This is a correctness feature, not a convenience one. OCR is never perfect,
 * and a user who sees a low score without seeing the garbled text behind it
 * has no way to tell whether the post is weak or the scan simply failed.
 *
 * `whitespace-pre-wrap` preserves the paragraph breaks the backend worked to
 * reconstruct; rendering them away would throw that work out.
 */
export function ExtractedTextCard({ extraction }: ExtractedTextCardProps) {
  const isLowConfidence =
    extraction.confidence !== null && extraction.confidence < LOW_CONFIDENCE_THRESHOLD;
  const text = extraction.text.trim();

  return (
    <SectionCard
      icon={FileSearch}
      title="Extracted text"
      description={EXTRACTION_METHOD_LABEL[extraction.method]}
      action={text ? <CopyButton value={text} label="Copy text" /> : undefined}
      meta={
        <>
          <Badge variant="secondary">{extraction.wordCount} words</Badge>
          {extraction.pageCount !== null && (
            <Badge variant="secondary">
              {extraction.pageCount} {extraction.pageCount === 1 ? "page" : "pages"}
            </Badge>
          )}
          {extraction.confidence !== null && (
            <Badge variant={isLowConfidence ? "warning" : "success"}>
              {extraction.confidence}% OCR confidence
            </Badge>
          )}
        </>
      }
    >
      <div className="space-y-4">
        {isLowConfidence && (
          <Alert variant="warning">
            <AlertTriangle aria-hidden="true" />
            <AlertDescription>
              The text was hard to read, so parts of it may be wrong. A sharper,
              higher-contrast scan will give better results.
            </AlertDescription>
          </Alert>
        )}

        <div className="bg-muted/40 max-h-96 overflow-y-auto rounded-lg border p-4">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {text || "No text was found in this document."}
          </p>
        </div>
      </div>
    </SectionCard>
  );
}
