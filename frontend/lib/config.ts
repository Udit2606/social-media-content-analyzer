/**
 * Every tunable value in the frontend, read from the environment in one place.
 *
 * Nothing else in the codebase touches `process.env`. Changing the backend URL
 * or the size cap is a one-line edit here, and a missing or malformed value
 * fails predictably in a single spot instead of silently somewhere downstream.
 *
 * NOTE: `NEXT_PUBLIC_*` variables are inlined by Next.js at BUILD time, not at
 * runtime. Changing one on your host requires a rebuild to take effect.
 */

/**
 * Backend origin, e.g. "https://analyzer-api.onrender.com".
 *
 * Deliberately has no fallback value. A hardcoded localhost default would
 * "work" in development and then fail confusingly in production; an empty
 * string surfaces as an explicit configuration error the moment it matters.
 */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");

const DEFAULT_MAX_FILE_SIZE_MB = 10;

/**
 * Guarded so a typo in the env var cannot silently disable the size limit.
 * `Number("ten")` is NaN, and every `size > NaN` comparison is false, which
 * would let files of any size through.
 */
function readMaxFileSizeMb(): number {
  const parsed = Number(process.env.NEXT_PUBLIC_MAX_FILE_SIZE_MB);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_MAX_FILE_SIZE_MB;
}

export const MAX_FILE_SIZE_MB = readMaxFileSizeMb();

export const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

/**
 * MIME types we accept.
 *
 * Must stay in step with the backend's own allowlist in
 * `backend/app/utils/file_validation.py`, which decides type by magic bytes.
 * Advertising a format here that the backend rejects means the user passes
 * client validation and then gets a 415 -- worse than never offering it.
 */
export const ACCEPTED_MIME_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
] as const;

/** Fallback check for browsers that report an empty `file.type`. */
export const ACCEPTED_EXTENSIONS = [
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
] as const;

export const FILE_INPUT_ACCEPT = ACCEPTED_MIME_TYPES.join(",");

/** Human-facing format list, used in the upload zone and in error copy. */
export const ACCEPTED_LABEL = "PDF, PNG or JPG";

/** OCR is slow and free-tier servers cold-start, so this is deliberately generous. */
export const REQUEST_TIMEOUT_MS = 90_000;

/** After this long we tell the user the server may be waking up. */
export const COLD_START_HINT_AFTER_MS = 10_000;
