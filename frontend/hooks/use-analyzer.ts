"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import {
  analyzeForPlatform,
  analyzeText,
  improvePost,
  uploadFile,
} from "@/lib/api";
import { AppError, toAppError } from "@/lib/errors";
import { validateFile } from "@/lib/validate-file";
import type {
  ContentAnalysis,
  ImprovedPost,
  Platform,
  PlatformOptimization,
  UploadResponse,
} from "@/types/analysis";

/**
 * The brain of the frontend: one explicit state machine for the whole journey.
 *
 * The user performs three actions, and the app makes four requests:
 *
 *   [Analyse]           -> POST /api/upload            (extract text)
 *                        -> POST /api/analyze-text      (general AI analysis)
 *   [switch platform]   -> POST /api/platform-analysis  (platform-fit advice)
 *   [Improve]           -> POST /api/improve            (AI rewrite)
 *
 * Extraction and analysis are one user action but two sequential requests, on
 * purpose: the extracted text is shown the moment it exists rather than being
 * held back until the slower AI call finishes.
 *
 *   idle ─select─▶ selected ─analyse─▶ extracting ─▶ analyzing ─▶ complete
 *                     ▲                    │             │           │
 *                     └──── cancel ────────┴─────────────┘           │
 *                     ▲                                              │
 *                     └──────────────── error ◀──────────────────────┘
 *
 * Platform optimization and improvement are deliberately NOT part of `phase`.
 * Both run after the general analysis is on screen and must not blank it out,
 * so each carries its own independent sub-state that can be loading or failed
 * while the analysis stays visible. `platform` lives in the reducer (not a
 * bare useState) because changing it is no longer a pure form update -- it
 * must clear the now-stale rewrite and optimization from the PREVIOUS
 * platform and kick off a fresh optimization fetch for the new one.
 */

export type AnalyzerPhase =
  | "idle"
  | "selected"
  | "extracting"
  | "analyzing"
  | "complete"
  | "error";

export type ImproveStatus = "idle" | "loading" | "done" | "error";
export type PlatformOptStatus = "idle" | "loading" | "done" | "error";

const DEFAULT_PLATFORM: Platform = "linkedin";

interface AnalyzerState {
  phase: AnalyzerPhase;
  /** Kept through the error state so "Try again" can resend the same file. */
  file: File | null;
  /** Extraction result. Populated during `analyzing`, before analysis exists. */
  upload: UploadResponse | null;
  analysis: ContentAnalysis | null;
  error: AppError | null;
  /** Non-blocking information, e.g. "only the first file was used". */
  notice: string | null;

  platform: Platform;

  improveStatus: ImproveStatus;
  improved: ImprovedPost | null;
  improveError: AppError | null;

  platformOptStatus: PlatformOptStatus;
  platformOptimization: PlatformOptimization | null;
  platformOptError: AppError | null;
}

type Action =
  | { type: "FILE_ACCEPTED"; file: File; notice: string | null }
  | { type: "FILE_REJECTED"; error: AppError }
  | { type: "EXTRACT_STARTED" }
  | { type: "EXTRACT_SUCCEEDED"; upload: UploadResponse }
  | { type: "ANALYZE_SUCCEEDED"; analysis: ContentAnalysis }
  | { type: "RUN_FAILED"; error: AppError }
  | { type: "RUN_CANCELLED" }
  | { type: "PLATFORM_SELECTED"; platform: Platform }
  | { type: "IMPROVE_STARTED" }
  | { type: "IMPROVE_SUCCEEDED"; improved: ImprovedPost }
  | { type: "IMPROVE_FAILED"; error: AppError }
  | { type: "IMPROVE_CANCELLED" }
  | { type: "PLATFORM_OPT_STARTED" }
  | { type: "PLATFORM_OPT_SUCCEEDED"; optimization: PlatformOptimization }
  | { type: "PLATFORM_OPT_FAILED"; error: AppError }
  | { type: "PLATFORM_OPT_CANCELLED" }
  | { type: "RESET" };

const initialState: AnalyzerState = {
  phase: "idle",
  file: null,
  upload: null,
  analysis: null,
  error: null,
  notice: null,
  platform: DEFAULT_PLATFORM,
  improveStatus: "idle",
  improved: null,
  improveError: null,
  platformOptStatus: "idle",
  platformOptimization: null,
  platformOptError: null,
};

/** Clearing a previous rewrite whenever the underlying content changes. */
const CLEARED_IMPROVEMENT = {
  improveStatus: "idle" as const,
  improved: null,
  improveError: null,
};

/** Clearing a previous platform-fit result whenever it goes stale. */
const CLEARED_PLATFORM_OPT = {
  platformOptStatus: "idle" as const,
  platformOptimization: null,
  platformOptError: null,
};

function reducer(state: AnalyzerState, action: Action): AnalyzerState {
  switch (action.type) {
    case "FILE_ACCEPTED":
      // A new file discards everything from the previous one, so the screen can
      // never show analysis, an optimization, or a rewrite belonging to a
      // different document.
      return {
        ...initialState,
        phase: "selected",
        file: action.file,
        notice: action.notice,
      };

    case "FILE_REJECTED":
      // No usable file, so fall all the way back to empty and show why.
      return { ...initialState, phase: "error", error: action.error };

    case "EXTRACT_STARTED":
      // The notice describes file selection, not results; clear it here so it
      // does not linger over the loading and success screens.
      return {
        ...state,
        phase: "extracting",
        upload: null,
        analysis: null,
        error: null,
        notice: null,
        ...CLEARED_IMPROVEMENT,
        ...CLEARED_PLATFORM_OPT,
      };

    case "EXTRACT_SUCCEEDED":
      // Extraction is done and analysis is starting. The text becomes visible
      // at this point -- this is the whole reason for two requests.
      return { ...state, phase: "analyzing", upload: action.upload };

    case "ANALYZE_SUCCEEDED":
      // Platform optimization is deliberately NOT triggered here. The effect
      // in useAnalyzer watches `phase` and fires it once analysis is on
      // screen, which keeps "when do we call the AI" logic in one place
      // instead of split between a reducer case and an effect.
      return { ...state, phase: "complete", analysis: action.analysis };

    case "RUN_FAILED":
      // `upload` is intentionally preserved: if extraction succeeded and only
      // the AI step failed, the user should keep the text they already have.
      return { ...state, phase: "error", error: action.error };

    case "RUN_CANCELLED":
      // Cancelling is not a failure: return to the pre-run state with the file
      // still selected, ready to try again.
      return {
        ...state,
        phase: state.file ? "selected" : "idle",
        upload: null,
        analysis: null,
        error: null,
      };

    case "PLATFORM_SELECTED":
      if (action.platform === state.platform) return state;
      // A rewrite or optimization for the OLD platform is actively wrong
      // under the NEW platform's heading, not just stale -- so both are
      // cleared rather than left on screen.
      return {
        ...state,
        platform: action.platform,
        ...CLEARED_IMPROVEMENT,
        ...CLEARED_PLATFORM_OPT,
      };

    case "IMPROVE_STARTED":
      return { ...state, improveStatus: "loading", improveError: null, improved: null };

    case "IMPROVE_SUCCEEDED":
      return { ...state, improveStatus: "done", improved: action.improved };

    case "IMPROVE_FAILED":
      return { ...state, improveStatus: "error", improveError: action.error };

    case "IMPROVE_CANCELLED":
      return { ...state, ...CLEARED_IMPROVEMENT };

    case "PLATFORM_OPT_STARTED":
      return {
        ...state,
        platformOptStatus: "loading",
        platformOptError: null,
        platformOptimization: null,
      };

    case "PLATFORM_OPT_SUCCEEDED":
      return {
        ...state,
        platformOptStatus: "done",
        platformOptimization: action.optimization,
      };

    case "PLATFORM_OPT_FAILED":
      return { ...state, platformOptStatus: "error", platformOptError: action.error };

    case "PLATFORM_OPT_CANCELLED":
      return { ...state, ...CLEARED_PLATFORM_OPT };

    case "RESET":
      return initialState;

    default:
      return state;
  }
}

export function useAnalyzer() {
  const [state, dispatch] = useReducer(reducer, initialState);

  // A pure form input, unrelated to the analysis flow's own state machine.
  const [instruction, setInstruction] = useState("");

  // Three independent controllers. Each async operation must be cancellable
  // without aborting the others, and a reset must abort all three.
  const runAbortRef = useRef<AbortController | null>(null);
  const improveAbortRef = useRef<AbortController | null>(null);
  const platformOptAbortRef = useRef<AbortController | null>(null);

  /**
   * Duplicate-submission guards.
   *
   * These MUST be refs, not derived booleans. React batches state updates, so
   * several clicks landing in the same tick all run against the pre-update
   * render -- every handler would see the same "not yet running" state and
   * fire its own request. A ref mutates synchronously, so the second call in
   * a burst sees the flag already set.
   *
   * Platform optimization has no such guard: see the comment on
   * runPlatformOptimization for why "abort and replace" is correct there
   * instead of "ignore while busy".
   */
  const runInFlightRef = useRef(false);
  const improveInFlightRef = useRef(false);

  useEffect(
    () => () => {
      runAbortRef.current?.abort();
      improveAbortRef.current?.abort();
      platformOptAbortRef.current?.abort();
    },
    [],
  );

  const isRunning = state.phase === "extracting" || state.phase === "analyzing";
  const isImproving = state.improveStatus === "loading";
  const isOptimizingPlatform = state.platformOptStatus === "loading";

  /** Validates the chosen file, then either stores it or raises an error. */
  const selectFile = useCallback(
    (files: FileList | File[] | null) => {
      // Guard: swapping the file mid-run would leave an in-flight request
      // writing results for a file the user has already replaced.
      if (isRunning) return;

      const list = files ? Array.from(files) : [];
      if (list.length === 0) return;

      const file = list[0];
      const validationError = validateFile(file);

      if (validationError) {
        dispatch({ type: "FILE_REJECTED", error: validationError });
        return;
      }

      dispatch({
        type: "FILE_ACCEPTED",
        file,
        notice:
          list.length > 1
            ? `${list.length} files were dropped. Only "${file.name}" was analysed.`
            : null,
      });
    },
    [isRunning],
  );

  /** Surface a problem that happened before we had a File at all (e.g. a folder). */
  const rejectFile = useCallback((error: AppError) => {
    dispatch({ type: "FILE_REJECTED", error });
  }, []);

  /**
   * The main action: extract, then analyse.
   *
   * Both requests share one AbortController so a single Cancel stops whichever
   * is in flight, and `signal.aborted` is re-checked after each await so a late
   * response from a cancelled run can never overwrite fresh state.
   */
  const analyze = useCallback(async () => {
    const file = state.file;
    if (!file || runInFlightRef.current) return;
    runInFlightRef.current = true;

    runAbortRef.current?.abort();
    const controller = new AbortController();
    runAbortRef.current = controller;

    dispatch({ type: "EXTRACT_STARTED" });

    try {
      const upload = await uploadFile(file, controller.signal);
      if (controller.signal.aborted) return;

      // Defensive: the backend returns 422 NO_TEXT_FOUND for empty extractions,
      // so this should be unreachable -- but sending an empty string to the AI
      // would waste a request and produce a meaningless analysis.
      if (!upload.extraction.text.trim()) {
        dispatch({
          type: "RUN_FAILED",
          error: new AppError({
            code: "NO_TEXT_FOUND",
            message: "We could not find any readable text in that file.",
            hint: "Try a clearer scan, or a PDF with selectable text.",
          }),
        });
        return;
      }

      dispatch({ type: "EXTRACT_SUCCEEDED", upload });

      const analysed = await analyzeText(upload.extraction.text, controller.signal);
      if (controller.signal.aborted) return;

      dispatch({ type: "ANALYZE_SUCCEEDED", analysis: analysed.analysis });
    } catch (error) {
      if (controller.signal.aborted) return;
      dispatch({ type: "RUN_FAILED", error: toAppError(error) });
    } finally {
      // Always released, on every exit path, so a second click after this run
      // genuinely finishes is a legitimate new request, not a no-op.
      runInFlightRef.current = false;
    }
  }, [state.file]);

  /** Generate a platform-tailored rewrite. Requires a completed analysis. */
  const improve = useCallback(async () => {
    const text = state.upload?.extraction.text;
    const analysis = state.analysis;
    if (!text || !analysis || improveInFlightRef.current) return;
    improveInFlightRef.current = true;

    improveAbortRef.current?.abort();
    const controller = new AbortController();
    improveAbortRef.current = controller;

    dispatch({ type: "IMPROVE_STARTED" });

    try {
      const result = await improvePost(
        { content: text, platform: state.platform, analysis, instruction },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      dispatch({ type: "IMPROVE_SUCCEEDED", improved: result.improved });
    } catch (error) {
      if (controller.signal.aborted) return;
      dispatch({ type: "IMPROVE_FAILED", error: toAppError(error) });
    } finally {
      improveInFlightRef.current = false;
    }
  }, [state.upload, state.analysis, state.platform, instruction]);

  /**
   * Assess the extracted text against `targetPlatform`'s norms.
   *
   * Not exposed directly -- triggered by the effect below, keyed on `phase`
   * and `platform`, so switching platforms always fetches fresh advice
   * without every call site having to remember to do so.
   *
   * Deliberately has NO "already in flight, ignore this call" guard, unlike
   * `analyze`/`improve`. Those guard against a duplicate CLICK of the same
   * action. This function is driven by an effect reacting to `platform`
   * changing, so each call represents a genuinely NEW desired outcome -- if
   * an "ignore while busy" guard were used here, switching platforms quickly
   * (x -> facebook -> linkedin before the first request finishes) would drop
   * every switch after the first, and the LinkedIn heading could end up
   * displaying X's stale score. Aborting the previous controller and racing
   * forward is the correct semantics: only the most recent request is ever
   * allowed to resolve, and every earlier one's `controller.signal.aborted`
   * check makes it a no-op when its late response arrives.
   */
  const runPlatformOptimization = useCallback(
    async (text: string, targetPlatform: Platform) => {
      platformOptAbortRef.current?.abort();
      const controller = new AbortController();
      platformOptAbortRef.current = controller;

      dispatch({ type: "PLATFORM_OPT_STARTED" });

      try {
        const result = await analyzeForPlatform(text, targetPlatform, controller.signal);
        if (controller.signal.aborted) return;
        dispatch({ type: "PLATFORM_OPT_SUCCEEDED", optimization: result.optimization });
      } catch (error) {
        if (controller.signal.aborted) return;
        dispatch({ type: "PLATFORM_OPT_FAILED", error: toAppError(error) });
      }
    },
    [],
  );

  /**
   * Fires platform optimization once analysis completes, and again every time
   * the user picks a different platform. This is the one place that decides
   * "when should we fetch platform advice" -- everything else just changes
   * `platform` and lets this react to it, the same way extracted text
   * appearing is what the loading skeleton reacts to rather than being told
   * to show itself.
   */
  useEffect(() => {
    if (state.phase !== "complete" || !state.upload) return;
    void runPlatformOptimization(state.upload.extraction.text, state.platform);
  }, [state.phase, state.platform, state.upload, runPlatformOptimization]);

  const selectPlatform = useCallback((platform: Platform) => {
    dispatch({ type: "PLATFORM_SELECTED", platform });
  }, []);

  const cancelRun = useCallback(() => {
    runAbortRef.current?.abort();
    runAbortRef.current = null;
    runInFlightRef.current = false;
    dispatch({ type: "RUN_CANCELLED" });
  }, []);

  const cancelImprove = useCallback(() => {
    improveAbortRef.current?.abort();
    improveAbortRef.current = null;
    improveInFlightRef.current = false;
    dispatch({ type: "IMPROVE_CANCELLED" });
  }, []);

  const retryPlatformOptimization = useCallback(() => {
    if (!state.upload) return;
    void runPlatformOptimization(state.upload.extraction.text, state.platform);
  }, [state.upload, state.platform, runPlatformOptimization]);

  const reset = useCallback(() => {
    runAbortRef.current?.abort();
    improveAbortRef.current?.abort();
    platformOptAbortRef.current?.abort();
    runAbortRef.current = null;
    improveAbortRef.current = null;
    platformOptAbortRef.current = null;
    runInFlightRef.current = false;
    improveInFlightRef.current = false;
    setInstruction("");
    dispatch({ type: "RESET" });
  }, []);

  return {
    ...state,
    isRunning,
    isImproving,
    isOptimizingPlatform,
    instruction,
    setInstruction,
    selectFile,
    rejectFile,
    analyze,
    improve,
    selectPlatform,
    retryPlatformOptimization,
    cancelRun,
    cancelImprove,
    reset,
  };
}
