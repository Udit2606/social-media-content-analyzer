"use client";

import { useEffect, useState } from "react";
import { Info, Loader2, XCircle } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { COLD_START_HINT_AFTER_MS } from "@/lib/config";

interface LoadingStateProps {
  onCancel: () => void;
}

/**
 * Everything the user sees while the backend is working.
 *
 * Does more than spin. It narrates progress with changing captions, offers a
 * way out, and after ten seconds explains that a free-tier server may be
 * waking up -- the difference between a wait that feels like work and a wait
 * that feels like a bug.
 *
 * The timers live here rather than in useAnalyzer because they are purely
 * cosmetic; the hook should not care how waiting is dressed up.
 */

/** Captions keyed to how long the request has been running. */
const STAGES = [
  { at: 0, label: "Uploading your file…" },
  { at: 1500, label: "Extracting text from the document…" },
  { at: 4500, label: "Running OCR, this can take a few seconds…" },
  { at: 8000, label: "Analysing engagement signals…" },
];

export function LoadingState({ onCancel }: LoadingStateProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const interval = setInterval(() => setElapsed(Date.now() - started), 500);
    return () => clearInterval(interval);
  }, []);

  const stage = [...STAGES].reverse().find((s) => elapsed >= s.at) ?? STAGES[0];
  const showColdStartHint = elapsed >= COLD_START_HINT_AFTER_MS;

  return (
    <div className="animate-fade-up space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 pt-5 sm:pt-6">
          <Loader2 className="text-primary size-5 shrink-0 animate-spin" aria-hidden="true" />

          {/*
            The live region is scoped to the status text only. Wrapping the
            whole block would make screen readers announce the decorative
            skeletons as they change.
          */}
          <div className="min-w-0 flex-1" role="status" aria-live="polite">
            <p className="text-sm font-medium">{stage.label}</p>
            <p className="text-muted-foreground text-xs">
              Your file is processed in memory and never stored.
            </p>
          </div>

          <Button type="button" variant="outline" size="sm" onClick={onCancel}>
            <XCircle aria-hidden="true" />
            Cancel
          </Button>
        </CardContent>
      </Card>

      {showColdStartHint && (
        <Alert variant="info">
          <Info aria-hidden="true" />
          <AlertDescription>
            The analyzer runs on a free tier and may be waking up. The first
            request after a quiet period can take up to a minute.
          </AlertDescription>
        </Alert>
      )}

      {/*
        Skeletons mirror the real results layout -- a full-width score card,
        then a two-column grid -- so content does not jump when data lands.
        Hidden from assistive tech because they carry no information.
      */}
      <div aria-hidden="true" className="space-y-4">
        <Card>
          <CardContent className="grid gap-8 pt-5 sm:grid-cols-[auto_1fr] sm:items-center sm:pt-6">
            <Skeleton className="mx-auto size-36 rounded-full" />
            <div className="space-y-4">
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="space-y-2">
                  <Skeleton className="h-3 w-24" />
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
    </div>
  );
}
