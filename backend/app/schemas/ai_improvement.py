"""The AI-facing contract for "Improve My Post".

Same role as ai_analysis.py: a plain, snake_case Pydantic model handed to
Gemini as `response_schema`, kept deliberately separate from the public
camelCase contract in schemas/analysis.py so either can change independently.

Field descriptions double as compact per-field prompt instructions -- Gemini
receives them as the JSON schema's property descriptions -- but the real
anti-hallucination and meaning-preservation rules live in the system
instruction in improvement_service.py, not here. This file only shapes the
output; it does not constrain what the model is allowed to say.
"""

from typing import List

from pydantic import BaseModel, Field


class AIImprovedPost(BaseModel):
    """The complete improved post, broken into its parts plus the assembled whole."""

    hook: str = Field(
        min_length=1,
        description="A rewritten, stronger opening line (or two), able to stand alone as the first thing a reader sees.",
    )
    body: str = Field(
        min_length=1,
        description="The rewritten main content, excluding the hook and the call to action. Every factual claim in the original must still be present here in some form.",
    )
    cta: str = Field(
        min_length=1,
        description="A stronger, platform-appropriate call to action -- a direct, specific ask of the reader.",
    )
    hashtags: List[str] = Field(
        max_length=15,
        description="Recommended hashtags without the leading '#', ordered by relevance, in a quantity appropriate to the target platform. Empty list if hashtags do not suit this platform or this post.",
    )
    full_post: str = Field(
        min_length=1,
        description="The complete, ready-to-publish post: hook, body and call to action combined with natural line breaks for the target platform, with hashtags included where that platform's convention expects them.",
    )
