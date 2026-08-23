"""Liveness endpoint.

Kept in api/ alongside the other routes rather than inlined into main.py, so
the "routes live in api/" rule holds without exception. (This file is a small
addition to the requested layout; the alternative was putting a route in
main.py, which the same rule forbids.)

It reports Tesseract and AI availability because the most common deployment
failure for this service is a container that installed the Python packages but
is missing the Tesseract binary, or was deployed without GEMINI_API_KEY set.
That turns a confusing "OCR/analysis mysteriously fails" report into a single
request that answers the question. Only a boolean and the model name are
exposed -- never the key itself.
"""

from fastapi import APIRouter

from app.config import settings
from app.schemas.analysis import HealthResponse
from app.services import analysis_service, ocr_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        tesseract_available=ocr_service.is_available(),
        tesseract_version=ocr_service.get_version(),
        ai_available=analysis_service.is_available(),
        ai_model=settings.gemini_model if analysis_service.is_available() else None,
    )
