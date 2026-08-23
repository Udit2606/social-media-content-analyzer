"""Platform-specific optimization advice, via Google Gemini.

Answers a different question from analysis_service.py. That one asks "is this a
good post?" and returns a platform-agnostic verdict. This one asks "how should
this post look on LinkedIn specifically?" -- and for identical input the answer
legitimately differs per platform, which is why it is a separate call rather
than extra fields on the general analysis.

The existing analysis pipeline is deliberately untouched by this module: it
imports nothing from analysis_service and analysis_service imports nothing from
here. Either can fail without affecting the other.

Same two-gate validation discipline as the other AI services: Gemini is
constrained to JSON via response_schema, and the raw response is independently
re-validated with Pydantic, with one retry on failure.

On the duplicated Gemini bootstrap: this is now the third module carrying the
same ~10-line "is a key configured, get me a client" block. Extracting it into
a shared module would mean editing analysis_service.py, which this feature is
required to leave intact. The duplication is small, contained, and a reasonable
target for a future refactor once these three stop changing.
"""

import logging
from typing import Optional

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import ValidationError

from app.config import settings
from app.schemas.ai_platform_optimization import AIPlatformOptimization
from app.schemas.analysis import PlatformOptimization
from app.utils import errors

logger = logging.getLogger(__name__)

# Platform norms, injected one at a time so the prompt stays small and the
# model is not tempted to average across platforms.
_PLATFORM_GUIDANCE = {
    "linkedin": (
        "LinkedIn: a professional audience reading in a work mindset. Posts of "
        "roughly 900-1300 characters perform well, broken into short "
        "paragraphs with line breaks for scannability. The first two lines "
        "show before the 'see more' fold. 1-3 relevant hashtags at the end. "
        "Insight, lessons learned and concrete numbers outperform hype."
    ),
    "instagram": (
        "Instagram: a visual-first, casual feed. The caption is truncated "
        "after roughly 125 characters, so the hook must land immediately. "
        "Warm, personal voice. Hashtags are expected and generous, roughly "
        "5-15, grouped at the end. Emoji are normal here, not unprofessional."
    ),
    "x": (
        "X (formerly Twitter): terse and fast-moving. A single post of under "
        "280 characters is ideal; anything longer needs to justify being a "
        "thread. No filler words, no throat-clearing preamble. At most 1-2 "
        "hashtags, and only where they add real discoverability."
    ),
    "facebook": (
        "Facebook: a broad, general audience in a social rather than "
        "professional mindset. Conversational storytelling works well, and "
        "length is flexible but front-loaded. Hashtags are rarely useful "
        "here -- 0-2 at most. Questions and relatable framing drive comments."
    ),
}

_SYSTEM_INSTRUCTION = """\
You are an expert social media strategist. You are given the text of a single \
post -- possibly extracted from a PDF or an image via OCR, so it may contain \
minor artifacts -- and ONE target platform. You assess how well the post suits \
that specific platform and recommend how to shape it for that platform.

Rules:
- Score platform FIT, not general writing quality. The same text can score
  high for one platform and low for another, and it should. A dense
  professional post scores well for LinkedIn and poorly for X.
- Every recommendation must be specific to the supplied platform and grounded
  in the actual text. Do not give generic advice that would read identically
  for a different platform or a different post.
- Recommendations describe what the post SHOULD become, not what it currently
  is. The user already has a general critique elsewhere; your job is the
  platform-specific angle.
- Do not invent facts about the post. You may suggest rewritten lines, but
  every claim in them must be traceable to the original text.
- Use the platform guidance provided as your reference for that platform's
  norms.

Respond with JSON only, matching the provided schema exactly."""

# Process-wide client, independent from the other AI services -- see the module
# docstring for why this is not shared.
_client: Optional[genai.Client] = None
_client_initialised = False


def is_available() -> bool:
    """Whether an optimization attempt is worth making.

    A configuration check (is a key set), not a network probe: there is no free
    way to verify a Gemini key without spending a real request.
    """
    return bool(settings.gemini_api_key.strip())


def _get_client() -> Optional[genai.Client]:
    global _client, _client_initialised
    if not _client_initialised:
        _client = genai.Client(api_key=settings.gemini_api_key) if is_available() else None
        _client_initialised = True
    return _client


async def analyze_for_platform(text: str, platform: str) -> PlatformOptimization:
    """Assess `text` against one platform's norms and recommend adjustments.

    Raises AppError on any failure; never returns None, never lets a raw
    exception escape.
    """
    if not is_available():
        raise errors.ai_unavailable()

    prompt = _build_prompt(text, platform)
    result = await _generate_with_retry(prompt)
    return _to_public_schema(result)


# -- Internals ----------------------------------------------------------


def _truncate(text: str) -> str:
    limit = settings.ai_max_input_chars
    if len(text) <= limit:
        return text
    logger.info(
        "Truncating text from %d to %d characters for platform analysis",
        len(text),
        limit,
    )
    return text[:limit]


def _build_prompt(text: str, platform: str) -> str:
    return (
        f"POST TEXT:\n{_truncate(text)}\n\n"
        f"TARGET PLATFORM: {platform}\n"
        f"{_PLATFORM_GUIDANCE.get(platform, '')}"
    )


async def _generate_with_retry(prompt: str) -> AIPlatformOptimization:
    """One attempt, then one retry if the model's answer fails validation.

    Mirrors the retry policy of the other AI services: a validation failure
    means Gemini returned syntactically valid JSON that nonetheless violates
    the schema -- rare given constrained decoding, but handled rather than
    assumed away.
    """
    last_error: Optional[ValidationError] = None

    for attempt in range(2):
        current = prompt if attempt == 0 else _repair_prompt(prompt, last_error)
        raw = await _call_gemini(current)

        try:
            return AIPlatformOptimization.model_validate_json(raw)
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "Platform optimization failed validation (attempt %d): %s",
                attempt + 1,
                exc,
            )

    logger.error(
        "Platform optimization failed validation twice; giving up. Last error: %s",
        last_error,
    )
    raise errors.ai_response_invalid()


def _repair_prompt(prompt: str, previous_error: ValidationError) -> str:
    return (
        f"{prompt}\n\n---\n"
        "Your previous response did not match the required schema: "
        f"{previous_error.error_count()} validation error(s). "
        "Respond again with corrected JSON that matches the schema exactly."
    )


async def _call_gemini(prompt: str) -> str:
    """One network call to Gemini. Returns the raw JSON text.

    Every failure becomes 503 AI_UNAVAILABLE, matching the other AI services:
    from the client's point of view "bad key", "rate limited" and "Gemini is
    down" are the same fact, even though the server log distinguishes them.
    """
    client = _get_client()
    config = genai_types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=AIPlatformOptimization,
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
        logger.exception("Gemini rejected the platform analysis request (client error)")
        raise errors.ai_unavailable()
    except genai_errors.ServerError:
        logger.warning("Gemini server error during platform analysis", exc_info=True)
        raise errors.ai_unavailable()
    except httpx.TimeoutException:
        logger.warning(
            "Gemini platform analysis did not respond within %ds",
            settings.ai_timeout_seconds,
        )
        raise errors.ai_unavailable()
    except Exception:
        logger.exception("Unexpected failure calling Gemini for platform analysis")
        raise errors.ai_unavailable()

    text = _extract_text(response)
    if not text:
        logger.warning(
            "Gemini returned no usable text for platform analysis (possibly safety-blocked)"
        )
        raise errors.ai_response_invalid()

    return text


def _extract_text(response: "genai_types.GenerateContentResponse") -> Optional[str]:
    try:
        return response.text
    except Exception:
        return None


def _to_public_schema(result: AIPlatformOptimization) -> PlatformOptimization:
    return PlatformOptimization(
        engagement_score=result.engagement_score,
        recommended_tone=result.recommended_tone,
        recommended_length=result.recommended_length,
        hook_recommendation=result.hook_recommendation,
        cta_recommendation=result.cta_recommendation,
        hashtag_recommendation=list(result.hashtag_recommendation),
    )
