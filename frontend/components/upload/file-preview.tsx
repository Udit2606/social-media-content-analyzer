"use client";

import { FileText, ImageIcon, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatBytes } from "@/lib/format";

interface FilePreviewProps {
  file: File;
  disabled?: boolean;
  onRemove: () => void;
}

/**
 * Confirms back to the user exactly what is about to be sent.
 *
 * Without it there is no way to tell whether the file the app holds is the one
 * they meant to pick. Pure display plus a single remove action; the parent
 * decides what removing means.
 */
export function FilePreview({ file, disabled, onRemove }: FilePreviewProps) {
  const isPdf =
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  const Icon = isPdf ? FileText : ImageIcon;

  return (
    <div className="bg-card flex items-center gap-3 rounded-lg border p-3 sm:p-4">
      <div
        aria-hidden="true"
        className="bg-secondary text-muted-foreground flex size-10 shrink-0 items-center justify-center rounded-md"
      >
        <Icon className="size-5" />
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={file.name}>
          {file.name}
        </p>
        <p className="text-muted-foreground text-xs">
          {isPdf ? "PDF document" : "Image"} · {formatBytes(file.size)}
        </p>
      </div>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        disabled={disabled}
        onClick={onRemove}
        aria-label={`Remove ${file.name} and choose a different file`}
      >
        <X aria-hidden="true" />
      </Button>
    </div>
  );
}
