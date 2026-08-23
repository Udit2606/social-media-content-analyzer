/**
 * One error vocabulary shared by validation, the API client and the UI.
 *
 * Every failure in the app becomes an `AppError` with a stable `code`, a
 * human-readable `message` and an optional `hint`. The UI renders the message
 * verbatim and never has to inspect a raw exception, and the code gives us a
 * machine-readable handle for branching or analytics later.
 */

export type ErrorCode =
  // Raised on the client, before any network call
  | "MISSING_API_URL"
  | "UNSUPPORTED_FILE_TYPE"
  | "FILE_TOO_LARGE"
  | "EMPTY_FILE"
  | "IS_DIRECTORY"
  // Raised by the transport layer
  | "NETWORK_ERROR"
  | "TIMEOUT"
  | "CANCELLED"
  | "INVALID_RESPONSE"
  // Mirrored from the backend's error codes
  | "BAD_REQUEST"
  | "NO_TEXT_FOUND"
  | "CORRUPTED_FILE"
  | "PASSWORD_PROTECTED"
  | "OCR_UNAVAILABLE"
  | "AI_UNAVAILABLE"
  | "AI_RESPONSE_INVALID"
  | "SERVER_ERROR"
  | "UNKNOWN";

export class AppError extends Error {
  readonly code: ErrorCode;
  readonly hint?: string;
  /** HTTP status when the error came from the server, otherwise null. */
  readonly status: number | null;
  /** Whether offering a "Try again" button makes sense for this failure. */
  readonly retryable: boolean;

  constructor(params: {
    code: ErrorCode;
    message: string;
    hint?: string;
    status?: number | null;
    retryable?: boolean;
  }) {
    super(params.message);
    this.name = "AppError";
    this.code = params.code;
    this.hint = params.hint;
    this.status = params.status ?? null;
    this.retryable = params.retryable ?? RETRYABLE_CODES.has(params.code);
  }
}

const RETRYABLE_CODES = new Set<ErrorCode>([
  "NETWORK_ERROR",
  "TIMEOUT",
  "SERVER_ERROR",
  "INVALID_RESPONSE",
  // The AI service being briefly unreachable, rate-limited, or returning an
  // unusable answer are all transient: a second attempt genuinely may work.
  "AI_UNAVAILABLE",
  "AI_RESPONSE_INVALID",
  "UNKNOWN",
]);
// OCR_UNAVAILABLE is deliberately NOT retryable: it means the Tesseract binary
// is missing from the server, which no amount of retrying will fix.

/**
 * Safety net for when the backend returns a code we do not recognise, or no
 * message at all. The user always sees a full sentence, never a raw code.
 */
export const FALLBACK_MESSAGES: Record<ErrorCode, string> = {
  MISSING_API_URL:
    "The analyzer is not configured with a backend URL, so it cannot process files.",
  UNSUPPORTED_FILE_TYPE: "That file type is not supported.",
  FILE_TOO_LARGE: "That file is too large.",
  EMPTY_FILE: "That file appears to be empty.",
  IS_DIRECTORY: "Please drop a single file, not a folder.",
  NETWORK_ERROR: "We could not reach the server. Check your connection and try again.",
  TIMEOUT: "The request took too long and was stopped.",
  CANCELLED: "The request was cancelled.",
  INVALID_RESPONSE: "The server sent back something we could not read.",
  BAD_REQUEST: "The server could not accept that request.",
  NO_TEXT_FOUND: "We could not find any readable text in that file.",
  CORRUPTED_FILE: "That file could not be opened. It may be damaged.",
  PASSWORD_PROTECTED: "That file is password protected.",
  OCR_UNAVAILABLE: "Text recognition is not available on the server right now.",
  AI_UNAVAILABLE: "Content analysis is not available right now.",
  AI_RESPONSE_INVALID:
    "The analysis service returned a response we could not use.",
  SERVER_ERROR: "Something went wrong on our end. Please try again.",
  UNKNOWN: "Something unexpected happened. Please try again.",
};

/** Normalise anything thrown anywhere in the app into an AppError. */
export function toAppError(error: unknown): AppError {
  if (error instanceof AppError) return error;
  return new AppError({
    code: "UNKNOWN",
    message: FALLBACK_MESSAGES.UNKNOWN,
  });
}
