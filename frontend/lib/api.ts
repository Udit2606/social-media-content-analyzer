import { API_URL, REQUEST_TIMEOUT_MS } from "@/lib/config";
import { AppError, FALLBACK_MESSAGES, type ErrorCode } from "@/lib/errors";
import type {
  AnalyzeTextResponse,
  ApiErrorBody,
  ContentAnalysis,
  ImprovedPost,
  ImproveResponse,
  Platform,
  PlatformAnalysisResponse,
  PlatformOptimization,
  UploadResponse,
} from "@/types/analysis";

/**
 * The only file in the app that knows the backend exists.
 *
 * Every component and hook calls these three functions instead of `fetch`, so
 * URL construction, timeouts, JSON parsing and error translation are written
 * once and behave identically everywhere. If the backend contract changes,
 * this file changes and nothing else does.
 *
 * It carries no knowledge of how the backend works internally -- not that it
 * is Python, not that it uses Tesseract or Gemini. It knows three URLs, three
 * request shapes and three response shapes.
 *
 * The flow is deliberately two calls rather than one:
 *   1. uploadFile()   -> extracted text, shown to the user immediately
 *   2. analyzeText()  -> AI analysis of that text
 * Using the backend's one-shot POST /api/analyze instead would mean the user
 * stares at a spinner through both extraction AND the AI call before seeing
 * anything. Splitting them lets the extracted text appear as soon as it
 * exists, which is most of the perceived speed.
 */

/** Error codes the backend is allowed to send. Anything else is normalised. */
const KNOWN_SERVER_CODES: ReadonlySet<string> = new Set<ErrorCode>([
  "BAD_REQUEST",
  "UNSUPPORTED_FILE_TYPE",
  "FILE_TOO_LARGE",
  "EMPTY_FILE",
  "NO_TEXT_FOUND",
  "CORRUPTED_FILE",
  "PASSWORD_PROTECTED",
  "OCR_UNAVAILABLE",
  "AI_UNAVAILABLE",
  "AI_RESPONSE_INVALID",
  "SERVER_ERROR",
]);

/* ------------------------------------------------------------------ */
/* Public API                                                          */
/* ------------------------------------------------------------------ */

/**
 * Step 1: upload a file and get its extracted text back.
 *
 * @param file   A PDF or image, already checked by the client-side validator.
 * @param signal Caller-owned AbortSignal, used to cancel an in-flight request
 *               when the user hits Cancel or the component unmounts.
 */
export async function uploadFile(
  file: File,
  signal?: AbortSignal,
): Promise<UploadResponse> {
  requireApiUrl();

  // FormData produces a multipart/form-data body, which is how binary files
  // travel over HTTP. We deliberately do NOT set a Content-Type header: the
  // browser must set it itself so it can append the multipart boundary.
  const body = new FormData();
  body.append("file", file);

  const response = await requestWithTimeout(`${API_URL}/api/upload`, {
    method: "POST",
    body,
    signal,
  });

  return parseResponse(response, isUploadResponse);
}

/** Step 2: analyse text that `uploadFile` already extracted. */
export async function analyzeText(
  text: string,
  signal?: AbortSignal,
): Promise<AnalyzeTextResponse> {
  requireApiUrl();

  const response = await requestWithTimeout(`${API_URL}/api/analyze-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });

  return parseResponse(response, isAnalyzeTextResponse);
}

/**
 * Step 3, on demand: generate a platform-tailored rewrite.
 *
 * The analysis is passed back to the backend deliberately -- its weaknesses
 * and suggestions are what the AI is told to fix, so the rewrite targets the
 * problems already shown to the user rather than rewriting freely.
 */
export async function improvePost(
  params: {
    content: string;
    platform: Platform;
    analysis: ContentAnalysis;
    instruction?: string;
  },
  signal?: AbortSignal,
): Promise<ImproveResponse> {
  requireApiUrl();

  const body: Record<string, unknown> = {
    content: params.content,
    platform: params.platform,
    analysis: params.analysis,
  };

  // Omit rather than send null: the backend treats the field as optional, and
  // an empty string would be a meaningless instruction to the model.
  const instruction = params.instruction?.trim();
  if (instruction) body.instruction = instruction;

  const response = await requestWithTimeout(`${API_URL}/api/improve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  return parseResponse(response, isImproveResponse);
}

/**
 * On demand: assess the post against one platform's norms.
 *
 * Independent from `improvePost` -- this returns advice (tone, length, hook,
 * CTA, hashtags to aim for), not a rewritten post. Deliberately does not take
 * the ContentAnalysis as input: platform fit is judged fresh against the
 * platform's own norms, not against the general critique.
 */
export async function analyzeForPlatform(
  text: string,
  platform: Platform,
  signal?: AbortSignal,
): Promise<PlatformAnalysisResponse> {
  requireApiUrl();

  const response = await requestWithTimeout(`${API_URL}/api/platform-analysis`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, platform }),
    signal,
  });

  return parseResponse(response, isPlatformAnalysisResponse);
}

/* ------------------------------------------------------------------ */
/* Transport                                                           */
/* ------------------------------------------------------------------ */

function requireApiUrl(): void {
  if (API_URL) return;
  throw new AppError({
    code: "MISSING_API_URL",
    message: FALLBACK_MESSAGES.MISSING_API_URL,
    hint: "Set NEXT_PUBLIC_API_URL in your environment and rebuild the app.",
    retryable: false,
  });
}

/**
 * `fetch` with a hard deadline, and every low-level failure translated into an
 * AppError. Combines our timeout with any caller-supplied signal so either can
 * cancel the request.
 */
async function requestWithTimeout(
  url: string,
  init: RequestInit,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  const external = init.signal;
  const forwardAbort = () => controller.abort();
  if (external) {
    if (external.aborted) forwardAbort();
    else external.addEventListener("abort", forwardAbort, { once: true });
  }

  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch {
    if (controller.signal.aborted) {
      // Distinguish "the user cancelled" from "we gave up waiting": only one
      // of those is worth showing as an error.
      const cancelledByUser = external?.aborted === true;
      throw new AppError({
        code: cancelledByUser ? "CANCELLED" : "TIMEOUT",
        message: cancelledByUser
          ? FALLBACK_MESSAGES.CANCELLED
          : "This is taking longer than expected, so we stopped waiting.",
        hint: cancelledByUser ? undefined : "Try again, or upload a smaller file.",
      });
    }
    // A rejected fetch that was not aborted means offline, DNS failure or CORS.
    throw new AppError({
      code: "NETWORK_ERROR",
      message: FALLBACK_MESSAGES.NETWORK_ERROR,
      hint: "The analyzer service may be starting up. Wait a moment and retry.",
    });
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", forwardAbort);
  }
}

/* ------------------------------------------------------------------ */
/* Response handling                                                   */
/* ------------------------------------------------------------------ */

/**
 * One parse path for all three endpoints, differing only in which runtime
 * shape check runs. Written once so a new endpoint cannot accidentally skip
 * error translation or validation.
 */
async function parseResponse<T>(
  response: Response,
  isValid: (value: unknown) => value is T,
): Promise<T> {
  const payload = await readJson(response);

  if (!response.ok) throw toServerError(response.status, payload);

  if (!isValid(payload)) {
    throw new AppError({
      code: "INVALID_RESPONSE",
      message: FALLBACK_MESSAGES.INVALID_RESPONSE,
      hint: "The analyzer returned a response this version of the app cannot read.",
      status: response.status,
    });
  }

  return payload;
}

/**
 * Read a JSON body without throwing when the server returned HTML, an empty
 * body, or a truncated stream. Returning null here means the shape check
 * below fails cleanly instead of a SyntaxError escaping to the UI.
 */
async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/** Map an HTTP status and error body onto our own error vocabulary. */
function toServerError(status: number, payload: unknown): AppError {
  const body = payload as Partial<ApiErrorBody> | null;
  const raw = body?.error;

  const code: ErrorCode =
    raw?.code && KNOWN_SERVER_CODES.has(raw.code)
      ? (raw.code as ErrorCode)
      : status >= 500
        ? "SERVER_ERROR"
        : statusFallback(status);

  return new AppError({
    code,
    message: raw?.message?.trim() || FALLBACK_MESSAGES[code],
    hint: raw?.hint,
    status,
  });
}

function statusFallback(status: number): ErrorCode {
  if (status === 400) return "BAD_REQUEST";
  if (status === 413) return "FILE_TOO_LARGE";
  if (status === 415) return "UNSUPPORTED_FILE_TYPE";
  if (status === 422) return "NO_TEXT_FOUND";
  if (status === 502) return "AI_RESPONSE_INVALID";
  if (status === 503) return "AI_UNAVAILABLE";
  return "UNKNOWN";
}

/* ------------------------------------------------------------------ */
/* Runtime validation                                                  */
/* ------------------------------------------------------------------ */

/**
 * TypeScript types vanish at build time, so these guards are the only thing
 * standing between a malformed payload and a crash inside a render. Each one
 * checks every branch the UI actually reads -- a partial check is worse than
 * none, because it lets a broken response through and then throws somewhere
 * far away with a useless stack trace.
 */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function hasNumberFields(value: unknown, keys: string[]): boolean {
  return isRecord(value) && keys.every((key) => typeof value[key] === "number");
}

function isUploadResponse(value: unknown): value is UploadResponse {
  if (!isRecord(value) || value.success !== true) return false;

  const { file, extraction } = value;

  if (!isRecord(file) || typeof file.name !== "string") return false;
  if (!isRecord(extraction) || typeof extraction.text !== "string") return false;
  if (typeof extraction.method !== "string") return false;

  return true;
}

function isContentAnalysis(value: unknown): value is ContentAnalysis {
  if (!isRecord(value)) return false;
  if (typeof value.overallScore !== "number") return false;

  const scoreKeys = [
    "hook",
    "clarity",
    "callToAction",
    "readability",
    "emotionalAppeal",
    "audienceRelevance",
    "hashtagQuality",
  ];
  if (!hasNumberFields(value.scores, scoreKeys)) return false;

  if (!isRecord(value.tone) || typeof value.tone.label !== "string") return false;
  if (!Array.isArray(value.tone.descriptors)) return false;

  if (!isRecord(value.sentiment) || typeof value.sentiment.label !== "string") {
    return false;
  }
  if (typeof value.sentiment.score !== "number") return false;

  if (!isRecord(value.audience) || typeof value.audience.primary !== "string") {
    return false;
  }
  if (typeof value.audience.readingLevel !== "string") return false;
  if (!Array.isArray(value.audience.segments)) return false;

  if (!isRecord(value.metrics)) return false;
  if (!hasNumberFields(value.metrics, ["wordCount", "characterCount", "sentenceCount"])) {
    return false;
  }
  if (typeof value.metrics.readabilityLevel !== "string") return false;

  return (
    Array.isArray(value.strengths) &&
    Array.isArray(value.weaknesses) &&
    Array.isArray(value.suggestions)
  );
}

function isAnalyzeTextResponse(value: unknown): value is AnalyzeTextResponse {
  if (!isRecord(value) || value.success !== true) return false;
  return isContentAnalysis(value.analysis);
}

function isImprovedPost(value: unknown): value is ImprovedPost {
  if (!isRecord(value)) return false;
  return (
    typeof value.hook === "string" &&
    typeof value.body === "string" &&
    typeof value.cta === "string" &&
    typeof value.fullPost === "string" &&
    Array.isArray(value.hashtags)
  );
}

function isImproveResponse(value: unknown): value is ImproveResponse {
  if (!isRecord(value) || value.success !== true) return false;
  if (typeof value.platform !== "string") return false;
  return isImprovedPost(value.improved);
}

function isPlatformOptimization(value: unknown): value is PlatformOptimization {
  if (!isRecord(value)) return false;
  return (
    typeof value.engagementScore === "number" &&
    typeof value.recommendedTone === "string" &&
    typeof value.recommendedLength === "string" &&
    typeof value.hookRecommendation === "string" &&
    typeof value.ctaRecommendation === "string" &&
    Array.isArray(value.hashtagRecommendation)
  );
}

function isPlatformAnalysisResponse(value: unknown): value is PlatformAnalysisResponse {
  if (!isRecord(value) || value.success !== true) return false;
  if (typeof value.platform !== "string") return false;
  return isPlatformOptimization(value.optimization);
}
