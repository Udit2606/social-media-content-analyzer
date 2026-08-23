""""Improve My Post": generate a platform-tailored, improved version.

Downstream of extraction and analysis, not a new upload. The frontend already
holds the original text and a ContentAnalysis from a prior POST /api/analyze;
this endpoint takes those plus a target platform and an optional instruction,
and returns a rewritten post.

This is the only JSON-body route in the API -- everything else is
multipart/form-data because it carries a file. There is nothing to upload
here, so a JSON body is the natural fit rather than forcing this through a
file-shaped interface.
"""

from fastapi import APIRouter

from app.schemas.analysis import ErrorResponse, ImproveRequest, ImproveResponse
from app.services import improvement_service

router = APIRouter(tags=["improve"])


@router.post(
    "/improve",
    response_model=ImproveResponse,
    summary="Generate a platform-tailored, improved version of a post",
    responses={
        400: {"model": ErrorResponse, "description": "Malformed request"},
        502: {"model": ErrorResponse, "description": "AI service returned an unusable response"},
        503: {"model": ErrorResponse, "description": "AI service unavailable"},
    },
)
async def improve(request: ImproveRequest) -> ImproveResponse:
    """Rewrite `request.content` for `request.platform`, using the supplied
    analysis to target known weaknesses and suggestions."""
    improved = await improvement_service.generate_improved_post(
        content=request.content,
        platform=request.platform,
        analysis=request.analysis,
        instruction=request.instruction,
    )

    return ImproveResponse(platform=request.platform, improved=improved)
