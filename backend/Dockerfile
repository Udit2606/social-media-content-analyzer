# Postora AI backend — production image for Render (or any Docker host).
#
# A plain Python buildpack cannot run this service: Tesseract OCR is a
# compiled system binary, not something `pip install` can provide. This image
# installs it explicitly via apt, which is the entire reason a Dockerfile is
# required here instead of a standard runtime.

FROM python:3.11-slim

# Prevents .pyc files and forces stdout/stderr to be unbuffered, so logs
# appear immediately in Render's log stream instead of being held back.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# tesseract-ocr: the OCR engine itself (see app/services/ocr_service.py).
# libgl1: a runtime dependency of Pillow's image codecs on Debian slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copied and installed before the rest of the source so Docker's layer cache
# is reused on every rebuild that only changes application code, not
# dependencies — meaningfully faster iteration once this is wired into CI.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Render sets $PORT at runtime; it is not fixed at build time. The shell form
# of CMD is required here specifically so that substitution happens.
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
