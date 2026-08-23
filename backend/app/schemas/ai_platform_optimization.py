"""The AI-facing contract for platform-specific optimization.

Same role as ai_analysis.py and ai_improvement.py: a plain, snake_case Pydantic
model handed to Gemini as `response_schema`, kept separate from the public
camelCase contract in schemas/analysis.py so either can change independently.

This is a SEPARATE dimension from the general analysis in ai_analysis.py, not a
replacement for it. The general analysis asks "is this a good post?"; this asks
"how should this post look on LinkedIn specifically?" -- and the answer changes
per platform for the same text, which is exactly why it cannot be folded into
the platform-agnostic result.

Field descriptions double as compact per-field prompt instructions, since
Gemini receives them as the JSON schema's property descriptions.
"""

from typing import List

from pydantic import BaseModel, Field


class AIPlatformOptimization(BaseModel):
    """How one specific post should be shaped for one specific platform."""

    engagement_score: int = Field(
        ge=0,
        le=100,
        description=(
            "How well this post, AS WRITTEN, would perform on this specific "
            "platform. This is a platform-fit score, not a general quality "
            "score: the same text can score high for LinkedIn and low for X. "
            "Judge it against that platform's norms and audience."
        ),
    )
    recommended_tone: str = Field(
        min_length=1,
        description=(
            "The tone this post SHOULD adopt for this platform, as a short "
            "phrase, e.g. 'Professional and insight-led' or 'Casual and "
            "conversational'. This is a recommendation, not a description of "
            "the current tone."
        ),
    )
    recommended_length: str = Field(
        min_length=1,
        description=(
            "The target length for this platform, in concrete terms the user "
            "can act on, e.g. '900-1300 characters, 3-4 short paragraphs' or "
            "'Under 280 characters, single post'. Include structure advice "
            "where it matters."
        ),
    )
    hook_recommendation: str = Field(
        min_length=1,
        description=(
            "One or two sentences of specific advice on the opening line for "
            "this platform, grounded in the actual text. Where useful, offer a "
            "concrete rewritten opener rather than generic guidance."
        ),
    )
    cta_recommendation: str = Field(
        min_length=1,
        description=(
            "One or two sentences of specific advice on the call to action for "
            "this platform, grounded in the actual text. Say what to ask the "
            "reader to do, and where to put it."
        ),
    )
    hashtag_recommendation: List[str] = Field(
        max_length=15,
        description=(
            "Recommended hashtags for this platform, WITHOUT the leading '#', "
            "in a quantity that suits the platform's convention (LinkedIn 1-3, "
            "Instagram 5-15, X 1-2, Facebook 0-2). Empty list if hashtags do "
            "not help this post on this platform."
        ),
    )
