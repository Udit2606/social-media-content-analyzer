"use client";

import { AlertTriangle, RotateCcw, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { AppError } from "@/lib/errors";

interface ErrorStateProps {
  error: AppError;
  /** Omitted when there is no file to resend, which hides the retry button. */
  onRetry?: () => void;
  onReset: () => void;
}

/**
 * The single place any failure is rendered, whether it came from client-side
 * validation, the network, or the backend.
 *
 * It shows the AppError's own message and hint, so error copy is written once
 * where the error is created rather than duplicated across components. A raw
 * status code or stack trace is never shown.
 *
 * `role="alert"` matters: without it, a screen-reader user who submits a file
 * and hits a failure gets complete silence.
 */
export function ErrorState({ error, onRetry, onReset }: ErrorStateProps) {
  return (
    <Card
      role="alert"
      className="animate-fade-up border-destructive/30 bg-destructive/5"
    >
      <CardContent className="flex flex-col gap-4 pt-5 sm:flex-row sm:items-start sm:pt-6">
        <div
          aria-hidden="true"
          className="bg-destructive/10 text-destructive flex size-10 shrink-0 items-center justify-center rounded-full"
        >
          <AlertTriangle className="size-5" />
        </div>

        <div className="min-w-0 flex-1 space-y-3">
          <div className="space-y-1">
            <p className="font-medium">We could not analyse that file</p>
            <p className="text-muted-foreground text-sm">{error.message}</p>
            {error.hint && <p className="text-muted-foreground text-sm">{error.hint}</p>}
          </div>

          <div className="flex flex-wrap gap-2">
            {error.retryable && onRetry && (
              <Button size="sm" onClick={onRetry}>
                <RotateCcw aria-hidden="true" />
                Try again
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={onReset}>
              <Upload aria-hidden="true" />
              Choose a different file
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
