"""One error vocabulary for the whole service.

Every expected failure is raised as an AppError carrying a stable machine
`code`, a human `message` and an optional `hint`. A single exception handler in
main.py turns those into the JSON envelope the frontend already understands:

    {"success": false, "error": {"code": "...", "message": "...", "hint": "..."}}

The codes here intentionally mirror the ones the frontend's lib/errors.ts
already knows about, so no translation layer is needed on either side.

Nothing in this module ever includes a stack trace, a file path or an
environment value in `message` -- those are logged server-side only.
"""

from typing import Optional


class ErrorCode:
    """String constants rather than an Enum, so they serialise as plain JSON."""

    BAD_REQUEST = "BAD_REQUEST"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    EMPTY_FILE = "EMPTY_FILE"
    CORRUPTED_FILE = "CORRUPTED_FILE"
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    NO_TEXT_FOUND = "NO_TEXT_FOUND"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    AI_RESPONSE_INVALID = "AI_RESPONSE_INVALID"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    SERVER_ERROR = "SERVER_ERROR"


class AppError(Exception):
    """An expected, user-facing failure with a known HTTP status."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        hint: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.hint = hint

    def to_payload(self) -> dict:
        error = {"code": self.code, "message": self.message}
        if self.hint:
            error["hint"] = self.hint
        return {"success": False, "error": error}


# -- Constructors for the common cases -----------------------------------
# Written once here so the same failure always produces identical wording,
# wherever in the codebase it is raised.


def unsupported_file_type(filename: str, accepted: str) -> AppError:
    return AppError(
        code=ErrorCode.UNSUPPORTED_FILE_TYPE,
        message=f'We cannot read "{filename}". Supported formats are {accepted}.',
        status_code=415,
        hint="Export your document as a PDF, or upload a screenshot of the post.",
    )


def file_too_large(filename: str, limit_mb: int) -> AppError:
    # No actual size is reported: we stop reading at the limit rather than
    # buffering the whole body, so the true size is genuinely unknown here.
    # Quoting the byte count we happened to reach would be misleading.
    return AppError(
        code=ErrorCode.FILE_TOO_LARGE,
        message=f'"{filename}" is larger than the {limit_mb} MB limit.',
        status_code=413,
        hint="Try compressing the file or exporting fewer pages.",
    )


def empty_file(filename: str) -> AppError:
    return AppError(
        code=ErrorCode.EMPTY_FILE,
        message=f'"{filename}" is empty (0 bytes).',
        status_code=400,
        hint="Check the file opens on your device, then try again.",
    )


def corrupted_file(filename: str) -> AppError:
    return AppError(
        code=ErrorCode.CORRUPTED_FILE,
        message=f'"{filename}" could not be opened. It may be damaged.',
        status_code=422,
        hint="Try re-exporting or re-saving the file.",
    )


def password_protected(filename: str) -> AppError:
    return AppError(
        code=ErrorCode.PASSWORD_PROTECTED,
        message=f'"{filename}" is password protected.',
        status_code=422,
        hint="Upload an unlocked copy of the document.",
    )


def no_text_found(is_image: bool) -> AppError:
    return AppError(
        code=ErrorCode.NO_TEXT_FOUND,
        message="We could not find any readable text in that file.",
        status_code=422,
        hint=(
            "Try a sharper, higher-contrast image."
            if is_image
            else "This document may contain only images with no readable text."
        ),
    )


def ocr_unavailable() -> AppError:
    return AppError(
        code=ErrorCode.OCR_UNAVAILABLE,
        message="Text recognition is not available on this server right now.",
        status_code=503,
        hint="Images cannot be processed until OCR is restored. PDFs still work.",
    )


def ai_unavailable() -> AppError:
    return AppError(
        code=ErrorCode.AI_UNAVAILABLE,
        message="Content analysis is not available right now.",
        status_code=503,
        hint="Please try again in a moment.",
    )


def ai_response_invalid() -> AppError:
    return AppError(
        code=ErrorCode.AI_RESPONSE_INVALID,
        message="The analysis service returned a response we could not use.",
        status_code=502,
        hint="Please try again.",
    )
