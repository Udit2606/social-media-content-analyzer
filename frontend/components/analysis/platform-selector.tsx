"use client";

import { PLATFORM_HINT, PLATFORM_LABEL, PLATFORM_ORDER } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { Platform } from "@/types/analysis";

interface PlatformSelectorProps {
  platform: Platform;
  onChange: (platform: Platform) => void;
  disabled?: boolean;
}

/**
 * The one platform picker for the whole results view.
 *
 * Extracted out of the Improve panel so a single selection drives both the
 * platform-optimization card and the rewrite below it -- two pickers on
 * screen for the same choice would be confusing and would let them disagree.
 *
 * Radio inputs rather than styled buttons: this is a single choice from a
 * fixed set, so arrow-key navigation and screen-reader grouping come from the
 * native input type instead of being rebuilt by hand.
 */
export function PlatformSelector({ platform, onChange, disabled }: PlatformSelectorProps) {
  return (
    <fieldset disabled={disabled} className="space-y-2">
      <legend className="text-muted-foreground mb-2 text-xs font-medium tracking-wide uppercase">
        Target platform
      </legend>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {PLATFORM_ORDER.map((option) => (
          <label
            key={option}
            className={cn(
              "flex cursor-pointer items-center justify-center rounded-lg border px-3 py-2 text-sm font-medium transition-colors",
              "has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-offset-2",
              platform === option
                ? "border-primary bg-primary/10 text-primary"
                : "border-border hover:bg-accent/50",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            <input
              type="radio"
              name="platform"
              value={option}
              checked={platform === option}
              onChange={() => onChange(option)}
              className="sr-only"
            />
            {PLATFORM_LABEL[option]}
          </label>
        ))}
      </div>

      <p className="text-muted-foreground text-xs">{PLATFORM_HINT[platform]}</p>
    </fieldset>
  );
}
