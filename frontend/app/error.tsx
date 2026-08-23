"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Route-level error boundary.
 *
 * Next.js renders this instead of a blank white page when any component in the
 * route throws during render. Before it existed, a malformed API response that
 * slipped past validation would take the whole page down with nothing on
 * screen and no way to recover.
 *
 * The real error is logged to the console for debugging but never shown, since
 * stack traces mean nothing to a user and can leak internals.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled error in analyzer route:", error);
  }, [error]);

  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <div
        aria-hidden="true"
        className="bg-destructive/10 text-destructive flex size-12 items-center justify-center rounded-full"
      >
        <AlertTriangle className="size-6" />
      </div>

      <div className="space-y-2">
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="text-muted-foreground text-sm">
          The analyzer hit an unexpected problem. Your file was not stored, so you
          can safely try again.
        </p>
      </div>

      <Button onClick={reset}>
        <RotateCcw aria-hidden="true" />
        Try again
      </Button>
    </main>
  );
}
