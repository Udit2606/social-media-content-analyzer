"""AI-powered "Improve My Post" generation, via Google Gemini.

Downstream of analysis: the caller already ran POST /api/analyze and holds a
ContentAnalysis identifying the post's weaknesses and suggestions. This
service folds that in as grounding -- the model is told what is already known
to be wrong, so generation targets fixing those specific issues rather than
producing a generic rewrite -- and returns a platform-tailored, ready-to-post
improvement: hook, body, CTA, hashtags, and the fully assembled post.

Same two-gate validation discipline as analysis_service.py: Gemini is
constrained to JSON via response_schema, and the raw response is
independently re-validated with Pydantic before it reaches the client, with
one retry on failure.

This module deliberately does NOT import from analysis_service.py or share
its Gemini client bootstrap, even though the ~10-line "is a key configured,
get me the client" pattern is duplicated between them. Deduplicating it would
mean touching analysis_service.py's already-tested internals for a change
unrelated to what analysis_service.py itself does -- out of scope for this
feature. The duplication is small, contained, and a reasonable target for a
future refactor if the two features are developed further together.
"""

import logging
from typing import Optional

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import ValidationError

from app.config import settings
from app.schemas.ai_improvement import AIImprovedPost
from app.schemas.analysis import ContentAnalysis, ImprovedPost
from app.utils import errors

logger = logging.getLogger(__name__)

_PLATFORM_GUIDANCE = {
    "linkedin": (
        "LinkedIn: a professional, thoughtful tone. Short paragraphs with line "
        "breaks for scannability. Roughly 900-1300 characters is typical for a "
        "well-performing post. At most 1-3 relevant hashtags, placed at the end."
    ),
    "instagram": (
        "Instagram: a warmer, more casual voice. The first line matters most, "
        "because the caption is truncated behind \"more\" -- put the strongest "
        "part of the hook there. Hashtags are expected and can be generous, "
        "roughly 5-15, placed at the end."
    ),
    "x": (
        "X (formerly Twitter): terse and punchy. Aim to fit in a single post, "
        "ideally under 280 characters if the content allows it without cutting "
        "meaning. No filler words. At most 1-2 hashtags, only if they add real "
        "discoverability."
    ),
    "facebook": (
        "Facebook: conversational and a little more personal, written for a "
        "broad general audience rather than a professional niche. Storytelling "
        "framing works well. Hashtags are rarely useful here -- use 0-2 at "
        "most, only if genuinely relevant."
    ),
}

_SYSTEM_INSTRUCTION = """\
You are an expert social media copywriter. You are given a post that has \
already been analysed, its identified weaknesses and suggestions, a target \
platform, and optionally a specific instruction from the user. Produce an \
improved version tailored to that platform.

Hard rules, non-negotiable:
- Preserve the original meaning and intent. Do not change what the post is
  fundamentally about.
- Do not invent facts. Never add a statistic, name, date, product detail, or
  claim that is not present in the original text, even if it would make the
  post read better. If the original has no concrete numbers, do not add any.
- Every claim in your output must be traceable back to the original content.
  You may rephrase, reorder, cut, and strengthen the presentation -- you may
  not add new substance.
- Use the supplied weaknesses and suggestions as your primary guide for what
  to fix. Do not ignore them, and do not "fix" things that were not flagged
  unless clearly necessary for the target platform.
- If a user instruction is provided, follow it, but the two rules above still
  apply: an instruction can change tone, length or structure, never invent
  facts.
- Genuinely match the target platform's style using the guidance provided.
  Do not write the same generic version regardless of platform: two versions
  of the same post for two different platforms should differ in tone,
  structure and length, not just in which hashtags are appended.

Respond with JSON only, matching the provided schema exactly."""

# A process-wide client, independent from analysis_service's -- see the
# module docstring for why this is not shared.
_client: Optional[genai.Client] = None
_client_initialised = False


def is_available() -> bool:
    """Whether an improvement attempt is worth making.

    A configuration check (is a key set), not a network probe -- there is no
    free way to verify a Gemini key without spending a real request.
    """
    return bool(settings.gemini_api_key.strip())


def _get_client() -> Optional[genai.Client]:
    global _client, _client_initialised
    if not _client_initialised:
        _client = genai.Client(api_key=settings.gemini_api_key) if is_available() else None
        _client_initialised = True
    return _client


async def generate_improved_post(
    content: str,
    platform: str,
    analysis: ContentAnalysis,
    instruction: Optional[str] = None,
) -> ImprovedPost:
    """Generate a platform-tailored, improved version of `content`.

    `analysis` is the ContentAnalysis already produced by POST /api/analyze --
    its weaknesses and suggestions are folded into the prompt as grounding.
    Raises AppError on any failure; never returns None, never lets a raw
    exception escape.
    """
    if not is_available():
        raise errors.ai_unavailable()

    prompt = _build_prompt(content, platform, analysis, instruction)
    result = await _generate_with_retry(prompt)
    return _to_public_schema(result)


# -- Internals ----------------------------------------------------------


def _truncate(text: str) -> str:
    limit = settings.ai_max_input_chars
    if len(text) <= limit:
        return text
    logger.info(
        "Truncating content from %d to %d characters for improvement", len(text), limit
    )
    return text[:limit]


def _build_prompt(
    content: str,
    platform: str,
    analysis: ContentAnalysis,
    instruction: Optional[str],
) -> str:
    text = _truncate(content)

    weaknesses = (
        "\n".join(f"- ({w.severity}) {w.title}: {w.detail}" for w in analysis.weaknesses)
        or None
    )
    suggestions = (
        "\n".join(f"- ({s.severity}) {s.title}: {s.detail}" for s in analysis.suggestions)
        or None
    )

    parts = [f"ORIGINAL POST:\n{text}"]
    parts.append(
        f"\nTARGET PLATFORM: {platform}\n"
        f"{_PLATFORM_GUIDANCE.get(platform, '')}"
    )

    if weaknesses or suggestions:
        parts.append(f"\nKNOWN WEAKNESSES (from prior analysis):\n{weaknesses or 'None identified.'}")
        parts.append(f"\nSUGGESTIONS TO ADDRESS (from prior analysis):\n{suggestions or 'None identified.'}")
    else:
        parts.append(
            "\nNo weaknesses or suggestions were identified in prior analysis "
            "-- this post is already working. Focus on tightening the "
            "language and adapting it cleanly for the target platform, "
            "without inventing problems to fix."
        )

    if instruction and instruction.strip():
        parts.append(f"\nUSER INSTRUCTION: {instruction.strip()}")

    return "\n".join(parts)


async def _generate_with_retry(prompt: str) -> AIImprovedPost:
    """One attempt, then one retry if the model's answer fails validation.

    Mirrors analysis_service's retry policy exactly: a validation failure here
    means Gemini returned syntactically valid JSON that nonetheless violates
    the schema -- rare given constrained decoding, but handled rather than
    assumed away. The retry appends the exact validation error to the prompt.
    """
    last_error: Optional[ValidationError] = None

    for attempt in range(2):
        current_prompt = prompt if attempt == 0 else _repair_prompt(prompt, last_error)
        raw = await _call_gemini(current_prompt)

        try:
            return AIImprovedPost.model_validate_json(raw)
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "Improved-post response failed validation (attempt %d): %s", attempt + 1, exc
            )

    logger.error(
        "Improved-post response failed validation twice; giving up. Last error: %s",
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

    Every failure mode is translated into a 503 AI_UNAVAILABLE, the same
    treatment analysis_service.py gives an equivalent failure: from the
    client's point of view "bad key", "rate limited", "network down" and
    "Gemini is having an outage" are all the same fact right now, even though
    the server log distinguishes them.
    """
    client = _get_client()
    config = genai_types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        response_mime_type="application/json",
        response_schema=AIImprovedPost,
        temperature=0.5,
        http_options=genai_types.HttpOptions(timeout=settings.ai_timeout_seconds * 1000),
    )

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        )
    except genai_errors.ClientError:
        logger.exception("Gemini rejected the improve request (client error)")
        raise errors.ai_unavailable()
    except genai_errors.ServerError:
        logger.warning("Gemini server error during improve", exc_info=True)
        raise errors.ai_unavailable()
    except httpx.TimeoutException:
        logger.warning("Gemini improve call did not respond within %ds", settings.ai_timeout_seconds)
        raise errors.ai_unavailable()
    except Exception:
        logger.exception("Unexpected failure calling Gemini for improve")
        raise errors.ai_unavailable()

    text = _extract_text(response)
    if not text:
        logger.warning("Gemini returned no usable text for improve (possibly safety-blocked)")
        raise errors.ai_response_invalid()

    return text


def _extract_text(response: "genai_types.GenerateContentResponse") -> Optional[str]:
    try:
        return response.text
    except Exception:
        return None


def _to_public_schema(result: AIImprovedPost) -> ImprovedPost:
    return ImprovedPost(
        hook=result.hook,
        body=result.body,
        cta=result.cta,
        hashtags=list(result.hashtags),
        full_post=result.full_post,
    )
