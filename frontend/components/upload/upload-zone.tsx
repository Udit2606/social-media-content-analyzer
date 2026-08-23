"use client";

import { useCallback, useRef, useState, type DragEvent } from "react";
import { FileText, FileUp, ImageIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ACCEPTED_LABEL, FILE_INPUT_ACCEPT, MAX_FILE_SIZE_MB } from "@/lib/config";
import { AppError, FALLBACK_MESSAGES } from "@/lib/errors";
import { cn } from "@/lib/utils";

interface UploadZoneProps {
  disabled?: boolean;
  onFilesSelected: (files: FileList | File[] | null) => void;
  onReject: (error: AppError) => void;
}

/**
 * The empty state: drop target and file picker in one control.
 *
 * Handles input only. It never validates and never uploads -- it hands raw
 * File objects to the parent, which owns every decision about them.
 *
 * Accessibility note: the outer element is a plain div with drag handlers and
 * a click shortcut, NOT `role="button"`. The keyboard and screen-reader path
 * is the real <Button> inside it. An earlier version put `role="button"` on
 * the wrapper with a focusable input inside, which produced two tab stops for
 * one control and nested an interactive element inside a button role. The
 * input is now hidden from both the tab order and the accessibility tree, and
 * is only ever opened programmatically.
 */
export function UploadZone({ disabled, onFilesSelected, onReject }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  // Dragging over a child element fires dragleave on the parent. Counting
  // enter/leave pairs is what stops the highlight from flickering.
  const dragDepth = useRef(0);

  const openPicker = useCallback(() => {
    if (!disabled) inputRef.current?.click();
  }, [disabled]);

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (disabled) return;
    dragDepth.current += 1;
    setIsDragging(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) {
      dragDepth.current = 0;
      setIsDragging(false);
    }
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepth.current = 0;
    setIsDragging(false);
    if (disabled) return;

    // A dropped folder arrives as a "file" with no usable content, so inspect
    // the entry first and give a specific message instead of failing later.
    const items = Array.from(event.dataTransfer.items ?? []);
    const hasDirectory = items.some((item) => item.webkitGetAsEntry?.()?.isDirectory);

    if (hasDirectory) {
      onReject(
        new AppError({
          code: "IS_DIRECTORY",
          message: FALLBACK_MESSAGES.IS_DIRECTORY,
          hint: "Open the folder and drag the document itself.",
        }),
      );
      return;
    }

    if (event.dataTransfer.files.length > 0) {
      onFilesSelected(event.dataTransfer.files);
    }
  };

  return (
    <div
      onClick={openPicker}
      onDragEnter={handleDragEnter}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      data-dragging={isDragging || undefined}
      className={cn(
        "flex flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors sm:py-16",
        disabled
          ? "border-border bg-muted/40 cursor-not-allowed opacity-60"
          : "border-border bg-card hover:border-primary/50 hover:bg-accent/40 cursor-pointer",
        isDragging && !disabled && "border-primary bg-primary/5",
      )}
    >
      {/*
        Hidden from the tab order and the accessibility tree. The visible
        Button below is the real control; this input is opened by script.
      */}
      <input
        ref={inputRef}
        type="file"
        accept={FILE_INPUT_ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        disabled={disabled}
        onChange={(event) => {
          onFilesSelected(event.target.files);
          // Reset so picking the same file twice in a row still fires onChange.
          event.target.value = "";
        }}
      />

      <div
        aria-hidden="true"
        className={cn(
          "flex size-14 items-center justify-center rounded-full transition-colors",
          isDragging
            ? "bg-primary/15 text-primary"
            : "bg-secondary text-muted-foreground",
        )}
      >
        <FileUp className="size-6" />
      </div>

      <div className="space-y-2">
        {/*
          A small branded kicker above the instruction, in the same
          uppercase-tracked-letterspacing style used for section labels
          elsewhere in the app (e.g. "TARGET PLATFORM") -- that treatment is
          what reads as a refined, considered product rather than a plain
          form control.
        */}
        <p className="text-primary text-xs font-semibold tracking-[0.2em] uppercase">
          Upload your content
        </p>
        <p className="text-base font-medium">
          {isDragging ? "Drop your file here" : "Drag and drop your file"}
        </p>
        <p className="text-muted-foreground text-sm">
          Upload a social post as a PDF or a screenshot
        </p>
      </div>

      <Button
        type="button"
        variant="outline"
        disabled={disabled}
        onClick={(event) => {
          // The wrapper also opens the picker; without this the click would
          // bubble and fire it a second time.
          event.stopPropagation();
          openPicker();
        }}
      >
        Browse files
      </Button>

      <p className="text-muted-foreground flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs">
        <span className="inline-flex items-center gap-1.5">
          <FileText className="size-3.5" aria-hidden="true" /> PDF
        </span>
        <span className="inline-flex items-center gap-1.5">
          <ImageIcon className="size-3.5" aria-hidden="true" /> PNG, JPG
        </span>
        <span>Up to {MAX_FILE_SIZE_MB} MB</span>
        <span className="sr-only">Accepted formats: {ACCEPTED_LABEL}.</span>
      </p>
    </div>
  );
}
