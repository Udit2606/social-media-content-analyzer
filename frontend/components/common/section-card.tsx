import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface SectionCardProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  /** Optional control rendered on the right of the header, e.g. a copy button. */
  action?: ReactNode;
  /** Optional row rendered under the title, e.g. a strip of badges. */
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Tailwind colour utility for the header icon, e.g. "text-success". */
  iconClassName?: string;
}

/**
 * The shared frame for every result section.
 *
 * Eight result cards previously repeated the same Card / CardHeader / icon /
 * title / description scaffolding. Extracting it means the section chrome is
 * defined once: a spacing or heading-level change happens in one file instead
 * of eight, and each section component is left containing only its own
 * content.
 */
export function SectionCard({
  icon: Icon,
  title,
  description,
  action,
  meta,
  children,
  className,
  iconClassName = "text-muted-foreground",
}: SectionCardProps) {
  return (
    <Card className={cn("animate-fade-up", className)}>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2 text-base">
              <Icon className={cn("size-4 shrink-0", iconClassName)} aria-hidden="true" />
              {title}
            </CardTitle>
            {description && <CardDescription>{description}</CardDescription>}
          </div>
          {action}
        </div>
        {meta && <div className="flex flex-wrap gap-2 pt-1">{meta}</div>}
      </CardHeader>

      <CardContent>{children}</CardContent>
    </Card>
  );
}
