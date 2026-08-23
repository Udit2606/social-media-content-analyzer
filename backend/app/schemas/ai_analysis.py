"""The contract between this service and the AI model.

Deliberately separate from schemas/analysis.py, which defines the public,
camelCase, HTTP-facing contract. This file is snake_case, has no aliasing, and
exists purely so a Pydantic class can be handed straight to Gemini as
`response_schema` -- the model is constrained to emit JSON matching these
field names and types.

Keeping the two contracts apart means either one can change without touching
the other: a prompt-engineering tweak to how we ask the model for a "hook"
score never has to think about frontend field naming, and vice versa.

Every numeric score is 0-100 int, matching the scale the frontend already
uses. Field descriptions are part of the prompt: Gemini receives them as the
schema's property descriptions, so they double as compact per-field
instructions rather than living only in the system prompt.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

SeverityLevel = Literal["high", "medium", "low"]
SentimentLabel = Literal["positive", "neutral", "negative", "mixed"]


class AIScoreBreakdown(BaseModel):
    hook: int = Field(ge=0, le=100, description="How strongly the opening line stops the scroll and earns a read.")
    clarity: int = Field(ge=0, le=100, description="How easily an average reader understands the point on one read.")
    call_to_action: int = Field(ge=0, le=100, description="How clearly the post asks the reader to do something specific.")
    readability: int = Field(ge=0, le=100, description="How easy the writing itself is to read: sentence length, jargon, structure.")
    emotional_appeal: int = Field(ge=0, le=100, description="How strongly the post evokes curiosity, excitement, pride, urgency, or another emotion.")
    audience_relevance: int = Field(ge=0, le=100, description="How precisely the post speaks to a specific, identifiable audience rather than a generic one.")
    hashtag_quality: int = Field(ge=0, le=100, description="Relevance and usefulness of the hashtags used. Score 50 if there are none and none are needed for this kind of post.")


class AITone(BaseModel):
    label: str = Field(description="A short phrase for the overall tone, e.g. 'Confident and informative'.")
    descriptors: List[str] = Field(
        min_length=1,
        max_length=4,
        description="1 to 4 single words or short phrases describing the tone, e.g. ['confident', 'technical'].",
    )


class AISentiment(BaseModel):
    label: SentimentLabel
    score: float = Field(ge=-1, le=1, description="Polarity from -1 (very negative) to 1 (very positive). 0 is neutral.")


class AIAudience(BaseModel):
    primary: str = Field(
        description="Who this post appears to be written for, in a short phrase, e.g. 'Software engineers and engineering managers'. Infer this from the content itself, not from assumptions.",
    )
    segments: List[str] = Field(
        max_length=4,
        description="Up to 4 narrower segments within that audience, e.g. ['backend engineers', 'platform teams']. Empty if the post is genuinely general-audience.",
    )
    reading_level: str = Field(
        description="A short phrase for how demanding the writing is, e.g. 'General', 'Professional / technical', 'Expert'.",
    )


class AIFinding(BaseModel):
    title: str = Field(description="A short, specific label for this point, under 8 words. Not generic.")
    detail: str = Field(description="One or two sentences explaining it, grounded in the actual text -- quote or paraphrase the relevant part.")


class AIWeakness(AIFinding):
    severity: SeverityLevel


class AISuggestion(AIFinding):
    severity: SeverityLevel
    example: Optional[str] = Field(
        default=None,
        description="An optional concrete rewritten line or phrase that demonstrates the fix.",
    )


class AIAnalysisResult(BaseModel):
    """The complete shape Gemini must return for one piece of content."""

    overall_score: int = Field(ge=0, le=100, description="Overall engagement potential, weighing all factors together.")
    scores: AIScoreBreakdown
    tone: AITone
    sentiment: AISentiment
    audience: AIAudience
    strengths: List[AIFinding] = Field(
        max_length=5,
        description="What the post already does well. Leave empty only if genuinely nothing stands out -- do not invent one.",
    )
    weaknesses: List[AIWeakness] = Field(
        max_length=5,
        description="What is holding the post back. Leave empty only if the post is genuinely strong -- do not invent one.",
    )
    suggestions: List[AISuggestion] = Field(
        max_length=6,
        description="Specific, actionable improvements, ordered most important first. Leave empty only if there is truly nothing to add.",
    )
