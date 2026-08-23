"""Upload and text-extraction route.

Deliberately thin. It receives the request, hands the file to the service layer
and returns the result. It contains no validation logic, no PDF knowledge and
no OCR knowledge -- all of that lives in services/ and utils/, which is what
makes those pieces testable without spinning up HTTP.
"""

from fastapi import APIRouter, File, UploadFile

from app.schemas.analysis import ErrorResponse, UploadResponse
from app.services import file_service

router = APIRouter(tags=["upload"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload a PDF or image and extract its text",
    responses={
        400: {"model": ErrorResponse, "description": "Empty or malformed file"},
        413: {"model": ErrorResponse, "description": "File exceeds the size limit"},
        415: {"model": ErrorResponse, "description": "Unsupported file type"},
        422: {"model": ErrorResponse, "description": "Unreadable, encrypted, or no text found"},
        503: {"model": ErrorResponse, "description": "OCR engine unavailable"},
    },
)
async def upload(file: UploadFile = File(..., description="A PDF, PNG or JPG file")):
    """Extract text from an uploaded document.

    PDFs are read with PyMuPDF. Images are read with Tesseract OCR. A PDF that
    turns out to be a scan is rendered to images and routed through OCR
    automatically.
    """
    return await file_service.process_upload(file)
