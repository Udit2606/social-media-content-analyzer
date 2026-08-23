import { BarChart3, FileText, Gauge, ScanText, Wand2 } from "lucide-react";

import { Analyzer } from "@/components/analyzer";

/**
 * The single route of the application: landing page and working dashboard in
 * one.
 *
 * A Server Component. The hero and the feature strip render on the server and
 * ship no JavaScript; only <Analyzer /> hydrates.
 *
 * Landing and tool are deliberately not split across two routes. The product
 * is one action, and making the user click "Get started" before they can
 * upload anything would add a step that buys nothing.
 */

const FEATURES = [
  {
    icon: FileText,
    title: "PDF parsing",
    description:
      "Reads text straight out of digital PDFs, keeping paragraph structure intact.",
  },
  {
    icon: ScanText,
    title: "OCR for images",
    description:
      "Screenshots and scans are read with optical character recognition.",
  },
  {
    icon: Gauge,
    title: "Engagement score",
    description: "Hook, clarity and call to action, each scored and explained.",
  },
  {
    icon: Wand2,
    title: "Rewritten post",
    description:
      "A ready-to-publish version with the suggestions already applied.",
  },
];

/**
 * Passed into <Analyzer /> as a slot so it can be hidden once the user has a
 * file selected. Keeping it defined here means it stays a Server Component.
 */
function FeatureStrip() {
  return (
    <section
      aria-label="What this tool does"
      className="grid gap-6 pt-10 sm:grid-cols-2 lg:grid-cols-4"
    >
      {FEATURES.map((feature) => (
        <div
          key={feature.title}
          className="border-border/60 bg-card/60 space-y-2 rounded-xl border p-4 backdrop-blur-sm"
        >
          <div
            aria-hidden="true"
            className="bg-primary/10 text-primary flex size-9 items-center justify-center rounded-lg"
          >
            <feature.icon className="size-4" />
          </div>
          <h3 className="text-sm font-semibold">{feature.title}</h3>
          <p className="text-muted-foreground text-sm leading-relaxed">
            {feature.description}
          </p>
        </div>
      ))}
    </section>
  );
}

export default function HomePage() {
  return (
    <main id="main" className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
      <div className="mx-auto max-w-4xl text-center">
        {/* Eyebrow pill. A plain element rather than <Badge>, because it needs
            its own elevated pill treatment rather than the compact tag style
            used inside result cards. */}
        <span className="border-border/70 bg-card/80 text-primary inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-semibold shadow-sm backdrop-blur">
          <BarChart3 className="size-4" aria-hidden="true" />
          Content intelligence, made clear
        </span>

        <h1 className="font-display mt-7 text-[2.5rem] leading-[0.98] font-extrabold text-balance sm:text-6xl lg:text-[4.5rem]">
          <span className="block">Turn content drafts into</span>
          <span className="text-primary block">stronger conversations.</span>
        </h1>

        <p className="text-muted-foreground mx-auto mt-6 max-w-2xl text-base leading-relaxed text-pretty sm:text-lg">
          Upload a PDF or a screenshot. postpilot.ai pulls out the text, scores how
          likely it is to earn engagement, and tells you exactly what to change.
        </p>
      </div>

      <div className="mt-12 sm:mt-14">
        <Analyzer emptyStateSlot={<FeatureStrip />} />
      </div>
    </main>
  );
}
