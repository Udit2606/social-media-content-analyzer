/**
 * Closing bar with the honesty note about how scoring works.
 *
 * Stating plainly that the analysis is heuristic rather than a trained model
 * belongs in the product, not just the README. It sets expectations before the
 * user reads a score and takes it as ground truth.
 */
export function SiteFooter() {
  return (
    <footer className="mt-16 border-t">
      <div className="text-muted-foreground mx-auto max-w-6xl space-y-2 px-4 py-6 text-xs sm:px-6">
        <p className="text-foreground font-medium">postpilot.ai</p>
        <p>
          Scoring is heuristic and based on widely published social media best
          practices, not on platform data or a trained model. Uploaded files are
          processed in memory and are never stored.
        </p>
      </div>
    </footer>
  );
}
