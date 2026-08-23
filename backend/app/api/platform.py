"""Platform-specific optimization route.

A second analysis dimension alongside POST /api/analyze-text, not a
replacement for it. That route returns a platform-agnostic critique; this one
returns advice for ONE named platform, and the same text yields different
answers for different platforms.

Kept as its own route so the two can be requested independently: the frontend
fetches the general analysis once, then re-fetches only this one when the user
switches platform, instead of paying for a full re-analysis.

A JSON body, like /api/analyze-text and /api/improve: there is no file here,
only text the caller already extracted.
"""

from fastapi import APIRouter

from app.schemas.analysis import (
    ErrorResponse,
    PlatformAnalysisRequest,
    PlatformAnalysisResponse,
)
from app.services import platform_service

router = APIRouter(tags=["platform"])


@router.post(
    "/platform-analysis",
    response_model=PlatformAnalysisResponse,
    summary="Assess a post against one platform's norms and recommend adjustments",
    responses={
        400: {"model": ErrorResponse, "description": "Missing text or unsupported platform"},
        502: {"model": ErrorResponse, "description": "AI service returned an unusable response"},
        503: {"model": ErrorResponse, "description": "AI service unavailable"},
    },
)
async def platform_analysis(
    request: PlatformAnalysisRequest,
) -> PlatformAnalysisResponse:
    """Score platform fit and recommend tone, length, hook, CTA and hashtags."""
    optimization = await platform_service.analyze_for_platform(
        text=request.text,
        platform=request.platform,
    )

    return PlatformAnalysisResponse(
        platform=request.platform,
        optimization=optimization,
    )
