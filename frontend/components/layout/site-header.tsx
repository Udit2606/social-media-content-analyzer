import { ScanText } from "lucide-react";

/**
 * Top bar carrying the postpilot.ai identity.
 *
 * Full-bleed rather than centred in a max-width container: the mark sits in
 * the actual top-left corner of the viewport, which is where a product logo is
 * expected to be. Centring it with the page content left it floating oddly
 * inset on wide screens.
 *
 * The wordmark is deliberately larger than a typical nav-bar logo -- this is
 * a small, single-page product, not a multi-section app where the header has
 * to compete with navigation links for space, so the brand can afford to be
 * the most visually confident thing in the bar. The icon badge is sized up to
 * match; a big wordmark next to a small icon reads as mismatched, not premium.
 *
 * A Server Component with no interactivity, so it costs nothing in JavaScript.
 * It also hosts the skip link, which must be the first focusable element on
 * the page for keyboard users to be able to bypass the header.
 */
export function SiteHeader() {
  return (
    <>
      <a
        href="#main"
        className="bg-primary text-primary-foreground sr-only rounded-md px-4 py-2 text-sm font-medium focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[100]"
      >
        Skip to main content
      </a>

      <header className="border-border/60 bg-background/70 sticky top-0 z-50 border-b backdrop-blur-xl">
        <div className="flex h-[72px] items-center gap-3 px-4 sm:px-6 lg:px-8">
          <div
            aria-hidden="true"
            className="from-primary flex size-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br to-violet-500 text-white shadow-sm"
          >
            <ScanText className="size-6" />
          </div>

          <div className="min-w-0">
            <p className="font-display truncate text-2xl leading-tight font-extrabold tracking-tight">
              postpilot.ai
            </p>
            <p className="text-muted-foreground hidden text-xs leading-tight sm:block">
              Create. Optimize. Engage.
            </p>
          </div>
        </div>
      </header>
    </>
  );
}
