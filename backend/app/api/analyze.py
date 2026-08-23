"""Extraction + AI engagement analysis, combined.

This is the full pipeline the frontend calls:

    upload -> PDF/OCR extraction -> extracted text -> AI analysis -> JSON

Extraction is delegated entirely to file_service.process_upload(), the exact
function /api/upload also calls -- so this route adds analysis on top of the
existing pipeline rather than re-implementing any of it. If extraction fails
(bad file, no text, OCR down), the request stops there with the same errors
/api/upload already returns; the AI is never called on a failed extraction.
"""

from fastapi import APIRouter, File, UploadFile

from app.schemas.analysis import (
    AnalyzeResponse,
    AnalyzeTextRequest,
    AnalyzeTextResponse,
    ErrorResponse,
)
from app.services import analysis_service, file_service

router = APIRouter(tags=["analysis"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Extract text from a document and analyse it for engagement",
    responses={
        400: {"model": ErrorResponse, "description": "Empty or malformed file"},
        413: {"model": ErrorResponse, "description": "File exceeds the size limit"},
        415: {"model": ErrorResponse, "description": "Unsupported file type"},
        422: {"model": ErrorResponse, "description": "Unreadable, encrypted, or no text found"},
        502: {"model": ErrorResponse, "description": "AI service returned an unusable response"},
        503: {"model": ErrorResponse, "description": "OCR or AI service unavailable"},
    },
)
async def analyze(file: UploadFile = File(..., description="A PDF, PNG or JPG file")):
    """Extract text from an uploaded document and score it for engagement."""
    extracted = await file_service.process_upload(file)

    analysis = await analysis_service.analyze_text(extracted.extraction.text)

    return AnalyzeResponse(
        file=extracted.file,
        extraction=extracted.extraction,
        analysis=analysis,
        processing=extracted.processing,
    )


@router.post(
    "/analyze-text",
    response_model=AnalyzeTextResponse,
    summary="Analyse already-extracted text for engagement",
    responses={
        400: {"model": ErrorResponse, "description": "Missing or empty text"},
        502: {"model": ErrorResponse, "description": "AI service returned an unusable response"},
        503: {"model": ErrorResponse, "description": "AI service unavailable"},
    },
)
async def analyze_text(request: AnalyzeTextRequest) -> AnalyzeTextResponse:
    """Analyse text that has already been extracted.

    The two-step counterpart to POST /api/analyze. A client that has already
    called POST /api/upload holds the extracted text, and re-uploading the
    file just to analyse it would repeat extraction -- re-running OCR on a
    multi-page scan for no benefit. This route skips straight to the AI step.

    A JSON body, like /api/improve: there is no file here, only text the
    caller already has.
    """
    analysis = await analysis_service.analyze_text(request.text)
    return AnalyzeTextResponse(analysis=analysis)
