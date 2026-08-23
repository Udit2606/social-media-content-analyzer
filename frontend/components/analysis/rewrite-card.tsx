import { Hash, Wand2 } from "lucide-react";

import { CopyButton } from "@/components/common/copy-button";
import { SectionCard } from "@/components/common/section-card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { PLATFORM_LABEL } from "@/lib/labels";
import type { ImprovedPost, Platform } from "@/types/analysis";

interface RewriteCardProps {
  improved: ImprovedPost;
  platform: Platform;
}

/**
 * The AI-rewritten post, from POST /api/improve.
 *
 * Shows the complete post first, because that is what the user actually wants
 * to copy and publish. The hook / body / CTA breakdown sits underneath as
 * supporting detail -- it explains how the rewrite is constructed and lets
 * someone lift just one part, but it is not the primary artefact.
 *
 * `whitespace-pre-wrap` throughout: line breaks are part of what makes a post
 * scannable, so rendering them away would destroy the thing being delivered.
 */
export function RewriteCard({ improved, platform }: RewriteCardProps) {
  const parts = [
    { label: "Hook", value: improved.hook },
    { label: "Body", value: improved.body },
    { label: "Call to action", value: improved.cta },
  ];

  return (
    <SectionCard
      icon={Wand2}
      iconClassName="text-primary"
      title="Improved post"
      description={`Rewritten for ${PLATFORM_LABEL[platform]}, targeting the weaknesses found above.`}
      action={<CopyButton value={improved.fullPost} label="Copy post" />}
    >
      <div className="space-y-5">
        <p className="bg-muted/50 rounded-lg border p-4 text-sm leading-relaxed whitespace-pre-wrap">
          {improved.fullPost}
        </p>

        <Separator />

        <div className="space-y-4">
          <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            How it breaks down
          </p>

          {parts.map((part) => (
            <div key={part.label} className="space-y-1">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium">{part.label}</p>
                <CopyButton value={part.value} label="Copy" />
              </div>
              <p className="text-muted-foreground text-sm leading-relaxed whitespace-pre-wrap">
                {part.value}
              </p>
            </div>
          ))}
        </div>

        {improved.hashtags.length > 0 && (
          <>
            <Separator />
            <div className="space-y-2">
              <p className="text-muted-foreground flex items-center gap-2 text-xs font-medium tracking-wide uppercase">
                <Hash className="size-3.5" aria-hidden="true" />
                Recommended hashtags
              </p>
              <div className="flex flex-wrap gap-2">
                {improved.hashtags.map((tag, index) => (
                  <Badge key={`${tag}-${index}`} variant="secondary">
                    #{tag}
                  </Badge>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </SectionCard>
  );
}
