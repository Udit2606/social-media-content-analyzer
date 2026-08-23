"""Request and response models.

These are the wire contract. Field names are serialised in camelCase to match
the TypeScript interfaces the frontend already defines, while staying snake_case
in Python -- `populate_by_name` allows both, and `alias_generator` handles the
conversion on output.

Keeping the contract in Pydantic models rather than hand-built dicts means
FastAPI generates accurate OpenAPI docs at /docs for free, and a typo in a field
name is caught at startup instead of by the frontend at runtime.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for every response model: snake_case in Python, camelCase on the wire."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# -- Health ---------------------------------------------------------------


class HealthResponse(CamelModel):
    status: str
    version: str
    # Surfaced so a deploy problem ("tesseract missing in the container") is
    # visible in one request instead of only when a user uploads an image.
    tesseract_available: bool
    tesseract_version: Optional[str] = None
    ai_available: bool
    ai_model: Optional[str] = None


# -- Upload / extraction ---------------------------------------------------


class FileInfo(CamelModel):
    name: str
    kind: str          # "pdf" | "image"
    size_bytes: int
    mime_type: str


class ExtractionResult(CamelModel):
    # "pdf_text" | "ocr_image" | "ocr_pdf_fallback"
    method: str
    text: str
    page_count: Optional[int] = None
    word_count: int
    character_count: int
    # 0-100 for OCR, None when the text came from a digital PDF.
    confidence: Optional[float] = None


class ProcessingInfo(CamelModel):
    duration_ms: int
    engine: str
    # Human-readable note on how the text was obtained, useful for debugging
    # a surprising result without reading the server logs.
    notes: str


class UploadResponse(CamelModel):
    success: bool = True
    file: FileInfo
    extraction: ExtractionResult
    processing: ProcessingInfo


# -- AI analysis -------------------------------------------------------------
#
# The public, camelCase mirror of app.schemas.ai_analysis. Kept as a separate
# set of models rather than reusing the AI-facing ones directly, so the wire
# contract (what the frontend sees) and the model contract (what Gemini must
# produce) can evolve independently. analysis_service.py is the only place
# that converts between the two.


class ScoreBreakdown(CamelModel):
    hook: int
    clarity: int
    call_to_action: int
    readability: int
    emotional_appeal: int
    audience_relevance: int
    hashtag_quality: int


class ToneAnalysis(CamelModel):
    label: str
    descriptors: List[str]


class SentimentAnalysis(CamelModel):
    label: str  # "positive" | "neutral" | "negative" | "mixed"
    score: float


class AudienceInsight(CamelModel):
    primary: str
    segments: List[str]
    reading_level: str


class Finding(CamelModel):
    id: str
    title: str
    detail: str


class Weakness(Finding):
    severity: str  # "high" | "medium" | "low"


class Suggestion(Finding):
    severity: str
    example: Optional[str] = None


class ContentMetrics(CamelModel):
    """Deterministic text statistics. Computed in text_metrics.py by plain
    arithmetic and the Flesch Reading Ease formula -- never by the AI model.
    Every field here is reproducible: the same text always yields the same
    numbers, which is not true of anything Gemini produces.
    """

    character_count: int
    word_count: int
    sentence_count: int
    avg_words_per_sentence: float
    reading_time_seconds: int
    # Flesch Reading Ease, 0-100. Higher means easier to read.
    readability_score: float
    # Short human label bucketed from readability_score, e.g. "Easy to read".
    readability_level: str


class ContentAnalysis(CamelModel):
    overall_score: int
    scores: ScoreBreakdown
    tone: ToneAnalysis
    sentiment: SentimentAnalysis
    audience: AudienceInsight
    strengths: List[Finding]
    weaknesses: List[Weakness]
    suggestions: List[Suggestion]
    metrics: ContentMetrics


class AnalyzeResponse(CamelModel):
    success: bool = True
    file: FileInfo
    extraction: ExtractionResult
    analysis: ContentAnalysis
    processing: ProcessingInfo


class AnalyzeTextRequest(CamelModel):
    """Body for POST /api/analyze-text.

    Exists so a caller that has ALREADY extracted text (via POST /api/upload)
    can analyse it without re-uploading the file and paying for extraction a
    second time. /api/analyze remains the one-shot file route for callers that
    want both steps in a single request.
    """

    # Not length-capped here: analysis_service truncates to AI_MAX_INPUT_CHARS
    # rather than rejecting a legitimately long document outright.
    text: str = Field(min_length=1)


class AnalyzeTextResponse(CamelModel):
    success: bool = True
    analysis: ContentAnalysis


# -- Improve My Post ---------------------------------------------------------
#
# Downstream of analysis, not a file upload: the caller already has extracted
# text and a ContentAnalysis from a prior POST /api/analyze, and asks for a
# platform-tailored, improved version. This is the first JSON-body endpoint in
# the API -- everything before it is multipart/form-data because it carries a
# file; this one carries only text and structured data that already exist on
# the frontend, so there is nothing to upload.

Platform = Literal["linkedin", "instagram", "x", "facebook"]


class ImproveRequest(CamelModel):
    # The original extracted text. Not length-capped here: a legitimately
    # long post is truncated by improvement_service, not rejected outright --
    # the same policy /api/analyze already applies to extracted text.
    content: str = Field(min_length=1)
    platform: Platform
    # The ContentAnalysis this same post already received from /api/analyze.
    # Its weaknesses and suggestions are what the AI is told to fix, rather
    # than rewriting the post freely.
    analysis: ContentAnalysis
    instruction: Optional[str] = Field(default=None, max_length=500)


class ImprovedPost(CamelModel):
    hook: str
    body: str
    cta: str
    hashtags: List[str]
    full_post: str


class ImproveResponse(CamelModel):
    success: bool = True
    platform: str  # "linkedin" | "instagram" | "x" | "facebook"
    improved: ImprovedPost


# -- Platform-specific optimization ------------------------------------------
#
# A second, independent analysis dimension. ContentAnalysis above is
# platform-agnostic: it judges the post on its own terms. This one judges the
# same text against ONE platform's norms, and the answer legitimately differs
# per platform for identical input -- which is why it is a separate model and a
# separate call rather than extra fields on ContentAnalysis.
#
# Kept deliberately out of ContentAnalysis so the existing analysis pipeline is
# untouched by this feature.


class PlatformOptimization(CamelModel):
    """How one post should be shaped for one platform."""

    # Platform FIT, not general quality: the same text can score 80 for
    # LinkedIn and 30 for X.
    engagement_score: int
    recommended_tone: str
    recommended_length: str
    hook_recommendation: str
    cta_recommendation: str
    # Without the leading "#", matching ImprovedPost.hashtags.
    hashtag_recommendation: List[str]


class PlatformAnalysisRequest(CamelModel):
    # Not length-capped here: platform_service truncates to AI_MAX_INPUT_CHARS
    # rather than rejecting a legitimately long document, matching the policy
    # of every other text-in endpoint.
    text: str = Field(min_length=1)
    platform: Platform


class PlatformAnalysisResponse(CamelModel):
    success: bool = True
    platform: Platform
    optimization: PlatformOptimization


# -- Errors ----------------------------------------------------------------


class ErrorDetail(CamelModel):
    code: str
    message: str
    hint: Optional[str] = None


class ErrorResponse(CamelModel):
    success: bool = False
    error: ErrorDetail
