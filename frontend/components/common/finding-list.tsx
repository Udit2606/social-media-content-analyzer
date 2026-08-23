import { CheckCircle2, AlertCircle, Lightbulb } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { SEVERITY_BADGE, SEVERITY_LABEL, SEVERITY_ORDER } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { Severity } from "@/types/analysis";

/** The minimum shape this list can render. Severity is optional. */
interface ListItem {
  id: string;
  title: string;
  detail: string;
  severity?: Severity;
  /**
   * Null as well as undefined: Pydantic serialises an unset Optional field as
   * JSON `null`, so the backend genuinely sends `"example": null`.
   */
  example?: string | null;
}

interface FindingListProps {
  items: ListItem[];
  /** Controls the icon, colour and whether items are numbered. */
  variant: "strength" | "weakness" | "suggestion";
  emptyMessage: string;
}

const VARIANTS = {
  strength: { icon: CheckCircle2, tone: "text-success", numbered: false },
  weakness: { icon: AlertCircle, tone: "text-warning", numbered: false },
  suggestion: { icon: Lightbulb, tone: "text-primary", numbered: true },
} as const;

/**
 * Renders strengths, weaknesses and suggestions with one component.
 *
 * All three are the same data shape -- id, title, detail, optionally a
 * severity -- and differ only in icon, colour and numbering. Three separate
 * list implementations would be three places to fix the same bug, so they
 * share this one and pass a `variant`.
 *
 * Items carrying a severity are sorted highest-impact first here rather than
 * trusting the backend's ordering, so the most important item is always read
 * first regardless of what order the API returns.
 */
export function FindingList({ items, variant, emptyMessage }: FindingListProps) {
  const { icon: Icon, tone, numbered } = VARIANTS[variant];

  if (items.length === 0) {
    return <p className="text-muted-foreground text-sm">{emptyMessage}</p>;
  }

  const ordered = [...items].sort((a, b) => {
    if (!a.severity || !b.severity) return 0;
    return SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
  });

  const ListTag = numbered ? "ol" : "ul";

  return (
    <ListTag className="space-y-4">
      {ordered.map((item, index) => (
        <li
          key={item.id}
          className="flex gap-3 border-b border-border pb-4 last:border-0 last:pb-0"
        >
          {numbered ? (
            <span
              aria-hidden="true"
              className="bg-secondary text-secondary-foreground mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-medium tabular-nums"
            >
              {index + 1}
            </span>
          ) : (
            <Icon className={cn("mt-0.5 size-4 shrink-0", tone)} aria-hidden="true" />
          )}

          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium">{item.title}</p>
              {item.severity && (
                <Badge variant={SEVERITY_BADGE[item.severity]}>
                  {SEVERITY_LABEL[item.severity]}
                </Badge>
              )}
            </div>

            <p className="text-muted-foreground text-sm">{item.detail}</p>

            {item.example && (
              <p className="bg-muted/60 mt-2 rounded-md px-3 py-2 text-sm italic">
                {item.example}
              </p>
            )}
          </div>
        </li>
      ))}
    </ListTag>
  );
}
