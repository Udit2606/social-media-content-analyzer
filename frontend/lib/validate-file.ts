import {
  ACCEPTED_EXTENSIONS,
  ACCEPTED_LABEL,
  ACCEPTED_MIME_TYPES,
  MAX_FILE_SIZE_BYTES,
  MAX_FILE_SIZE_MB,
} from "@/lib/config";
import { AppError } from "@/lib/errors";
import { formatBytes } from "@/lib/format";

/**
 * Client-side gate that runs the moment a file is chosen or dropped.
 *
 * This exists purely for speed of feedback: rejecting a 40 MB video here saves
 * the user a pointless upload. It is NOT a security control. The backend
 * re-checks type (by magic bytes) and size on every request, because anything
 * the browser reports is user-controlled and trivially faked.
 *
 * Returns null when the file is acceptable, or an AppError describing the problem.
 */
export function validateFile(file: File): AppError | null {
  if (file.size === 0) {
    return new AppError({
      code: "EMPTY_FILE",
      message: `"${file.name}" is empty (0 bytes).`,
      hint: "Check the file opens on your device, then try again.",
    });
  }

  if (file.size > MAX_FILE_SIZE_BYTES) {
    return new AppError({
      code: "FILE_TOO_LARGE",
      message: `"${file.name}" is ${formatBytes(file.size)}. The limit is ${MAX_FILE_SIZE_MB} MB.`,
      hint: "Try compressing the file or exporting fewer pages.",
    });
  }

  const mimeOk = (ACCEPTED_MIME_TYPES as readonly string[]).includes(file.type);
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  const extensionOk = (ACCEPTED_EXTENSIONS as readonly string[]).includes(extension);

  // Some browsers report an empty `type` for files dragged from certain apps,
  // so we accept the file if EITHER signal looks right.
  if (!mimeOk && !extensionOk) {
    return new AppError({
      code: "UNSUPPORTED_FILE_TYPE",
      message: `We cannot read "${file.name}". Supported formats are ${ACCEPTED_LABEL}.`,
      hint: "Export your document as a PDF, or upload a screenshot of the post.",
    });
  }

  return null;
}
