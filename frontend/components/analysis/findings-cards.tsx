import { AlertCircle, Lightbulb, Sparkles } from "lucide-react";

import { FindingList } from "@/components/common/finding-list";
import { SectionCard } from "@/components/common/section-card";
import type { Strength, Suggestion, Weakness } from "@/types/analysis";

/**
 * Strengths, weaknesses and improvement suggestions.
 *
 * Three exports in one file because they are the same component three times
 * over -- a SectionCard wrapping a FindingList -- differing only in copy and
 * icon. Splitting them across three files would spread near-identical
 * boilerplate without making anything easier to find.
 *
 * Each renders its own empty state rather than disappearing, so the layout
 * stays stable and "nothing here" is itself a clear message.
 */

export function StrengthsCard({ strengths }: { strengths: Strength[] }) {
  return (
    <SectionCard
      icon={Sparkles}
      iconClassName="text-success"
      title="Strengths"
      description="Keep these when you rewrite the post."
    >
      <FindingList
        items={strengths}
        variant="strength"
        emptyMessage="No clear strengths stood out. Work through the suggestions and analyse the post again."
      />
    </SectionCard>
  );
}

export function WeaknessesCard({ weaknesses }: { weaknesses: Weakness[] }) {
  return (
    <SectionCard
      icon={AlertCircle}
      iconClassName="text-warning"
      title="Weaknesses"
      description="What is holding this post back."
    >
      <FindingList
        items={weaknesses}
        variant="weakness"
        emptyMessage="No significant weaknesses were found in this post."
      />
    </SectionCard>
  );
}

export function SuggestionsCard({ suggestions }: { suggestions: Suggestion[] }) {
  return (
    <SectionCard
      icon={Lightbulb}
      iconClassName="text-primary"
      title="Improvement suggestions"
      description="Ordered by impact. Start at the top for the biggest gain."
    >
      <FindingList
        items={suggestions}
        variant="suggestion"
        emptyMessage="Nothing to change. This post already follows the practices we check for."
      />
    </SectionCard>
  );
}
