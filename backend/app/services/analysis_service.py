"""AI-powered engagement analysis, via Google Gemini.

Takes the text that file_service already extracted and returns a scored,
structured critique: an overall score, seven sub-scores, tone, sentiment,
strengths, weaknesses and improvement suggestions.

Two things this module is careful about:

1. Structured output over free text. Gemini is called with
   `response_mime_type="application/json"` and `response_schema=AIAnalysisResult`
   (see schemas/ai_analysis.py), which constrains generation to that shape at
   the model level. The response is then independently re-validated with
   Pydantic here -- constrained decoding is best-effort, not a guarantee, so
   the real gate is the validation call, not the schema hint.

2. Every external-dependency failure becomes a typed AppError, never a raw
   exception or a stack trace reaching the client. Missing key, network
   failure, timeout, and "the model answered but the answer was unusable" are
   four different situations and are reported as such.
"""

import logging
from typing import Optional

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import ValidationError

from app.config import settings
from app.schemas.ai_analysis import AIAnalysisResult
from app.schemas.analysis import (
    AudienceInsight,
    ContentAnalysis,
    ContentMetrics,
    Finding,
    ScoreBreakdown,
    SentimentAnalysis,
    Suggestion,
    ToneAnalysis,
    Weakness,
)
from app.services import text_metrics
from app.utils import errors

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = """\
You are an expert social media content analyst and copywriting coach. You are
given the text of a single social media post -- possibly extracted from a PDF
or an image via OCR, so it may contain minor artifacts -- and you evaluate its
likely engagement performance.

Be honest and calibrated, not flattering. A weak post should score low. A
strong post should score high. Ground every strength, weakness and suggestion
in the actual text: refer to specific words or lines, not generic advice that
could apply to any post. Never invent a strength or weakness that is not
actually present -- an empty list is a valid and often correct answer.

If the text is very short, still produce your best judgement rather than
refusing; note brevity itself as a factor if it matters.

Respond with JSON only, matching the provided schema exactly."""

# A process-wide client. The SDK is safe to reuse across requests; creating a
# fresh one per call would add nothing but overhead. None means "no API key
# configured", checked by is_available() before any call is attempted.
_client: Optional[genai.Client] = None
_client_initialised = False


def is_available() -> bool:
    """Whether an analysis attempt is even worth making.

    This is a configuration check, not a network probe -- unlike OCR's
    is_available(), there is no cheap local way to verify a Gemini API key
    without spending a real request against the quota. "Available" here means
    "a key is configured", which is what /api/health reports.
    """
    return bool(settings.gemini_api_key.strip())


def _get_client() -> genai.Client:
    global _client, _client_initialised
    if not _client_initialised:
        _client = genai.Client(api_key=settings.gemini_api_key) if is_available() else None
        _client_initialised = True
    return _client


async def analyze_text(text: str) -> ContentAnalysis:
    """Run engagement analysis over extracted text and return the public,
    camelCase result. Raises AppError on any failure -- never returns None and
    never lets a raw exception escape.

    The AI call and the deterministic metrics are two independent sources
    combined into one response, not one pipeline: `metrics` is computed on
    the FULL original text (never truncated -- word/character counts must
    describe the actual content, not the shortened version sent to the
    model) and does not depend on Gemini succeeding at all. It is only
    unavailable here because this function fails closed on `is_available()`
    before either happens; see the module docstring in text_metrics.py for
    why the counting itself needs no AI.
    """
    if not is_available():
        raise errors.ai_unavailable()

    prompt_text = _truncate(text)

    result = await _generate_with_retry(prompt_text)
    metrics = text_metrics.compute_metrics(text)
    return _to_public_schema(result, metrics)


# -- Internals --------------------------------------------------------------


def _truncate(text: str) -> str:
    limit = settings.ai_max_input_chars
    if len(text) <= limit:
        return text
    logger.info("Truncating extracted text from %d to %d characters for analysis", len(text), limit)
    return text[:limit]


async def _generate_with_retry(text: str) -> AIAnalysisResult:
    """One attempt, then one retry if the model's answer fails validation.

    A validation failure here means Gemini returned syntactically valid JSON
    that nonetheless violates our schema (a score out of range, an empty
    required field) -- rare given constrained decoding, but not impossible.
    The retry appends the exact validation error to the prompt, which is
    usually enough to correct it. Two failures in a row is treated as the
    model being unable to produce a usable answer right now.
    """
    last_error: Optional[ValidationError] = None

    for attempt in range(2):
        prompt = text if attempt == 0 else _repair_prompt(text, last_error)

        raw = await _call_gemini(prompt)

        try:
            return AIAnalysisResult.model_validate_json(raw)
        except ValidationError as exc:
            last_error = exc
            logger.warning("AI response failed validation (attempt %d): %s", attempt + 1, exc)

    logger.error("AI response failed validation twice; giving up. Last error: %s", last_error)
    raise errors.ai_response_invalid()


def _repair_prompt(text: str, previous_error: ValidationError) -> str:
    return (
        f"{text}\n\n"
        "---\n"
        "Your previous response did not match the required schema: "
        f"{previous_error.error_count()} validation error(s). "
        "Respond again with corrected JSON that matches the schema exactly."
    )


async def _call_gemini(prompt: str) -> str:
    """One network call to Gemini. Returns the raw JSON text.

    Every failure mode below is translated into a 503 AI_UNAVAILABLE: from the
    client's point of view, "invalid key", "rate limited", "network down" and
    "Gemini is having an outage" are all the same fact -- analysis cannot be
    performed right now -- even though the server log distinguishes them for
    whoever is operating this service.
    """
    client = _get_client()
    config = genai_types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=AIAnalysisResult,
        temperature=0.4,
        http_options=genai_types.HttpOptions(timeout=settings.ai_timeout_seconds * 1000),
    )

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        )
    except genai_errors.ClientError:
        # 4xx from Gemini: bad/expired key, quota exhausted, request rejected.
        # An operator problem, not the current user's -- logged with the real
        # detail, reported to the client as a generic unavailability.
        logger.exception("Gemini rejected the request (client error)")
        raise errors.ai_unavailable()
    except genai_errors.ServerError:
        logger.warning("Gemini server error", exc_info=True)
        raise errors.ai_unavailable()
    except httpx.TimeoutException:
        logger.warning("Gemini call did not respond within %ds", settings.ai_timeout_seconds)
        raise errors.ai_unavailable()
    except Exception:
        # Any other failure: DNS, TLS, connection refused, an SDK-internal
        # problem. Still an external-dependency failure from the caller's
        # perspective, so it gets the same client-facing error.
        logger.exception("Unexpected failure calling Gemini")
        raise errors.ai_unavailable()

    text = _extract_text(response)
    if not text:
        logger.warning("Gemini returned no usable text (possibly safety-blocked)")
        raise errors.ai_response_invalid()

    return text


def _extract_text(response: "genai_types.GenerateContentResponse") -> Optional[str]:
    """Pull the text out of a response defensively.

    `.text` can raise or return None when the model produced no candidates --
    most commonly because the safety filters blocked the input or the output.
    That is treated as "invalid response" rather than crashing the request.
    """
    try:
        return response.text
    except Exception:
        return None


def _to_public_schema(result: AIAnalysisResult, metrics: ContentMetrics) -> ContentAnalysis:
    """Map the AI-facing (snake_case, unaliased) result onto the public,
    camelCase response contract, adding the stable ids the frontend needs for
    list rendering. The AI is never asked to invent ids itself -- one more
    thing that could be malformed for no benefit.
    """
    return ContentAnalysis(
        overall_score=result.overall_score,
        scores=ScoreBreakdown(
            hook=result.scores.hook,
            clarity=result.scores.clarity,
            call_to_action=result.scores.call_to_action,
            readability=result.scores.readability,
            emotional_appeal=result.scores.emotional_appeal,
            audience_relevance=result.scores.audience_relevance,
            hashtag_quality=result.scores.hashtag_quality,
        ),
        tone=ToneAnalysis(label=result.tone.label, descriptors=result.tone.descriptors),
        sentiment=SentimentAnalysis(label=result.sentiment.label, score=result.sentiment.score),
        audience=AudienceInsight(
            primary=result.audience.primary,
            segments=list(result.audience.segments),
            reading_level=result.audience.reading_level,
        ),
        strengths=[
            Finding(id=f"strength-{i + 1}", title=item.title, detail=item.detail)
            for i, item in enumerate(result.strengths)
        ],
        weaknesses=[
            Weakness(
                id=f"weakness-{i + 1}", title=item.title, detail=item.detail, severity=item.severity
            )
            for i, item in enumerate(result.weaknesses)
        ],
        suggestions=[
            Suggestion(
                id=f"suggestion-{i + 1}",
                title=item.title,
                detail=item.detail,
                severity=item.severity,
                example=item.example,
            )
            for i, item in enumerate(result.suggestions)
        ],
        metrics=metrics,
    )
