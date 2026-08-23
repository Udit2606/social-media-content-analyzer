"""Application entrypoint: wiring only.

Creates the FastAPI app, configures CORS, registers the routers and installs
the exception handlers that guarantee every failure leaves this service in the
same JSON shape. No business logic lives here by design.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import analyze, health, improve, platform, upload
from app.config import settings
from app.utils.errors import AppError, ErrorCode

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Extracts text from PDFs and images for the postpilot.ai frontend. "
        "PDFs are parsed with PyMuPDF; images are read with Tesseract OCR."
    ),
    docs_url="/docs",
)

# -- CORS -----------------------------------------------------------------
#
# Origins come from the CORS_ALLOW_ORIGINS environment variable, so the same
# image runs locally and on Render without a code change.
#
# We do NOT use allow_origins=["*"]. Two reasons:
#
#   1. A wildcard lets any website on the internet script requests against this
#      API from a visitor's browser. Nothing here is authenticated, so the risk
#      is abuse of compute (OCR is expensive) rather than data theft -- but a
#      free-tier instance is exactly the kind of thing that gets drained.
#   2. A wildcard is incompatible with credentialed requests. Even though this
#      service uses no cookies today, pinning the allowlist now means adding
#      auth later does not require rediscovering this rule.
#
# The cost of the allowlist is one environment variable per deployment, which
# is also a useful forcing function: a forgotten origin fails loudly in the
# browser console rather than silently working for everyone.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,
)

# -- Routes ---------------------------------------------------------------
app.include_router(health.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(improve.router, prefix="/api")
app.include_router(platform.router, prefix="/api")


# -- Exception handlers ---------------------------------------------------
#
# Three handlers cover every path out of this service, so a client never
# receives an unstructured error or a stack trace.


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    """Expected failures: already carry a code, a message and a status."""
    logger.info("Handled error %s: %s", exc.code, exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI rejected the request shape.

    The API has two request shapes now: multipart/form-data with a `file`
    field (/api/upload, /api/analyze) and a JSON body (/api/improve). The hint
    used to hardcode the multipart case, which was correct until /api/improve
    existed and became actively misleading for it. `loc` in the first error
    tells us which shape was actually expected, so the hint matches whichever
    endpoint was called instead of assuming every request carries a file.
    """
    error_list = exc.errors()
    logger.info("Request validation failed: %s", error_list)

    mentions_file = any("file" in error.get("loc", ()) for error in error_list)
    hint = (
        "Send the document as multipart/form-data under the field name 'file'."
        if mentions_file
        else "Check that the request body matches the documented schema for this endpoint."
    )

    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": {
                "code": ErrorCode.BAD_REQUEST,
                "message": "The request was not formed correctly.",
                "hint": hint,
            },
        },
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """404s and any other HTTPException, normalised into our envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": ErrorCode.BAD_REQUEST if exc.status_code < 500 else ErrorCode.SERVER_ERROR,
                "message": str(exc.detail),
            },
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
    """Last resort.

    The real exception is logged with a traceback for debugging; the client is
    told only that something went wrong. Leaking a stack trace would expose
    file paths, library versions and internal structure.
    """
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": ErrorCode.SERVER_ERROR,
                "message": "Something went wrong on our end. Please try again.",
            },
        },
    )
