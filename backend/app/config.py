"""Application configuration, loaded once from the environment.

Every tunable value lives here. Nothing else in the codebase reads os.environ,
so changing a limit or an allowed origin is a one-line edit in a predictable
place, and a malformed value fails at startup instead of halfway through a
request.

Values are read from environment variables or a local .env file. Secrets are
never logged and never returned in an API response.
"""

from functools import lru_cache
from typing import List, Tuple

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- Service ---------------------------------------------------------
    app_name: str = "postpilot.ai API"
    app_version: str = "1.0.0"
    debug: bool = False

    # -- CORS ------------------------------------------------------------
    # Comma-separated list, e.g. "http://localhost:3000,https://postpilot-ai.vercel.app".
    # Deliberately not defaulted to "*": see main.py for the reasoning.
    cors_allow_origins: str = "http://localhost:3000"

    # -- Upload limits ---------------------------------------------------
    max_file_size_mb: int = 10

    # Guard against a malicious 5,000-page PDF pinning the CPU in OCR.
    max_ocr_pages: int = 10

    # Below this many characters per page, a PDF is assumed to be a scan
    # with no embedded text, and we fall back to OCR.
    scanned_pdf_char_threshold: int = 32

    # -- OCR -------------------------------------------------------------
    # Optional absolute path to the tesseract binary. Leave blank to use PATH.
    tesseract_cmd: str = ""
    ocr_language: str = "eng"

    # -- AI analysis -------------------------------------------------------
    # A free-tier key from https://aistudio.google.com/apikey. Backend-only:
    # never sent to the frontend, never included in a response, never logged.
    # Blank means "AI analysis is unavailable" -- the service still boots and
    # /api/upload (extraction only) keeps working.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    # Extracted text is truncated to this many characters before being sent to
    # the model, bounding both cost and the blast radius of a huge upload.
    ai_max_input_chars: int = 6000

    # Hard deadline for one call to the AI API.
    ai_timeout_seconds: int = 30

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def allowed_origins(self) -> List[str]:
        """Parse the comma-separated origin list into a clean list."""
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]

    # -- Accepted uploads -------------------------------------------------
    @property
    def allowed_mime_types(self) -> Tuple[str, ...]:
        return ("application/pdf", "image/png", "image/jpeg")

    @property
    def allowed_extensions(self) -> Tuple[str, ...]:
        return (".pdf", ".png", ".jpg", ".jpeg")


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the environment is parsed exactly once per process."""
    return Settings()


settings = get_settings()
