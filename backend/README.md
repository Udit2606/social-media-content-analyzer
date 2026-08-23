# postpilot.ai — Backend

FastAPI service that extracts text from PDFs and images for the postpilot.ai
frontend.

- **PDFs** are parsed with **PyMuPDF** (native text objects, layout preserved).
- **Images** are read with **Tesseract OCR** via pytesseract, with Pillow
  pre-processing.
- **Scanned PDFs** are detected automatically, rasterised, and routed through OCR.
- **Engagement analysis** is powered by **Google Gemini** (`gemini-3.6-flash`,
  free tier), with the response validated against a Pydantic schema before it
  ever reaches the client.

`POST /api/analyze` runs the full pipeline: extraction, then AI analysis, in
one call. `POST /api/upload` remains extraction-only, for testing extraction
without spending an AI request. `POST /api/improve` is downstream of both: it
takes the original text plus the analysis already produced and generates a
platform-tailored, improved rewrite.

---

## Requirements

- Python 3.9+
- **Tesseract OCR** — a separate compiled binary, not a Python package.
  `pytesseract` is only a wrapper; without the binary, image uploads return
  `503 OCR_UNAVAILABLE` while PDFs continue to work.
- **A Gemini API key** (free) — without it, `POST /api/analyze` returns
  `503 AI_UNAVAILABLE` while `POST /api/upload` (extraction only) keeps working.

```bash
# macOS
brew install tesseract

# Debian / Ubuntu
sudo apt-get install -y tesseract-ocr

# verify
tesseract --version
```

Get a free Gemini key at **https://aistudio.google.com/apikey** — no credit
card required. Put it in `.env` as `GEMINI_API_KEY`.

---

## Run locally

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/api/health

Confirm OCR is wired up:

```bash
curl -s http://127.0.0.1:8000/api/health
```

`tesseractAvailable` must be `true` before image uploads will work.
`aiAvailable` must be `true` before `/api/analyze` will return a real result.

### How the Tesseract binary is located

In order of precedence:

1. **`TESSERACT_CMD`**, if set — an operator saying exactly where the binary
   lives always wins, and is the only mechanism that works on an unusual host.
2. **`PATH`** — the normal case. A standard Homebrew or `apt` install needs no
   configuration at all.
3. **Standard install locations** — `/opt/homebrew/bin`, `/usr/local/bin`,
   `/opt/local/bin`, `/usr/bin`. This covers the case where the process was
   started with a stripped `PATH` (launchd, some supervisors, some CI runners),
   so `tesseract` works in your terminal but not in the server process.

No machine-specific path is hardcoded as a default, and a wrong `TESSERACT_CMD`
is logged and ignored rather than being fatal — PDFs keep working and image
uploads return a clear `503`.

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CORS_ALLOW_ORIGINS` | `http://localhost:3000` | Comma-separated browser origins allowed to call the API. No trailing slashes. |
| `MAX_FILE_SIZE_MB` | `10` | Upload size cap. Keep in sync with the frontend. |
| `MAX_OCR_PAGES` | `10` | Hard cap on pages rendered + OCR'd from a scanned PDF. |
| `TESSERACT_CMD` | *(blank)* | Absolute path to the binary. Leave blank unless needed — see below. |
| `OCR_LANGUAGE` | `eng` | Tesseract language pack. |
| `GEMINI_API_KEY` | *(blank)* | Free key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey). **Backend only** — never sent to the frontend. |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Any current Gemini model supporting structured JSON output. |
| `AI_MAX_INPUT_CHARS` | `6000` | Extracted text is truncated to this length before being sent to the model. |
| `AI_TIMEOUT_SECONDS` | `30` | Hard deadline for one AI call. |
| `DEBUG` | `false` | Verbose logging. Never enable in production. |

No secret is ever returned by an endpoint, embedded in the OpenAPI schema, or
written to a log — verified in `tests/test_api_analyze.py::TestKeyNeverLeaks`.

---

## Endpoints

### `GET /api/health`

```json
{
  "status": "ok",
  "version": "1.0.0",
  "tesseractAvailable": true,
  "tesseractVersion": "5.5.0",
  "aiAvailable": true,
  "aiModel": "gemini-3.6-flash"
}
```

### `POST /api/upload`

`multipart/form-data`, field name **`file`**. Accepts PDF, PNG, JPG/JPEG.

```bash
curl -X POST http://127.0.0.1:8000/api/upload -F "file=@post.pdf"
```

**200:**

```json
{
  "success": true,
  "file": {
    "name": "post.pdf",
    "kind": "pdf",
    "sizeBytes": 1228,
    "mimeType": "application/pdf"
  },
  "extraction": {
    "method": "pdf_text",
    "text": "We just shipped our biggest update yet.\n\nLatency is down 60%.",
    "pageCount": 1,
    "wordCount": 12,
    "characterCount": 62,
    "confidence": null
  },
  "processing": {
    "durationMs": 3,
    "engine": "PyMuPDF",
    "notes": "Extracted embedded text from 1 page(s)."
  }
}
```

`method` is one of `pdf_text`, `ocr_image`, `ocr_pdf_fallback`.
`confidence` is `0-100` for OCR results and `null` for native PDF text.

### `POST /api/analyze`

`multipart/form-data`, field name **`file`**. Runs the same extraction as
`/api/upload`, then sends the extracted text to Gemini for engagement
analysis. If extraction fails, the AI is never called.

```bash
curl -X POST http://127.0.0.1:8000/api/analyze -F "file=@post.pdf"
```

**200:**

```json
{
  "success": true,
  "file": {
    "name": "post.pdf",
    "kind": "pdf",
    "sizeBytes": 1228,
    "mimeType": "application/pdf"
  },
  "extraction": {
    "method": "pdf_text",
    "text": "We just shipped our biggest update yet.\n\nLatency is down 60%.",
    "pageCount": 1,
    "wordCount": 12,
    "characterCount": 62,
    "confidence": null
  },
  "analysis": {
    "overallScore": 68,
    "scores": {
      "hook": 55,
      "clarity": 78,
      "callToAction": 10,
      "readability": 72,
      "emotionalAppeal": 60,
      "audienceRelevance": 65,
      "hashtagQuality": 50
    },
    "tone": { "label": "Confident and informative", "descriptors": ["confident", "technical"] },
    "sentiment": { "label": "positive", "score": 0.4 },
    "strengths": [
      { "id": "strength-1", "title": "Concrete numbers", "detail": "Cites a specific 60% figure, which reads as credible." }
    ],
    "weaknesses": [
      { "id": "weakness-1", "title": "No closing ask", "detail": "Ends on a statement with nothing for the reader to respond to.", "severity": "high" }
    ],
    "suggestions": [
      {
        "id": "suggestion-1",
        "title": "Add a call to action",
        "detail": "Close with a direct question to invite replies.",
        "severity": "high",
        "example": "What's the hardest migration you've shipped?"
      }
    ]
  },
  "processing": {
    "durationMs": 3,
    "engine": "PyMuPDF",
    "notes": "Extracted embedded text from 1 page(s)."
  }
}
```

`method` is one of `pdf_text`, `ocr_image`, `ocr_pdf_fallback`.
`confidence` is `0-100` for OCR results and `null` for native PDF text.
All `scores` fields and `overallScore` are `0-100`; `sentiment.score` is `-1..1`.

### `POST /api/improve`

The only **JSON-body** route in the API — there is no file here, only text and
structured data the frontend already holds from a prior `/api/analyze` call.

```bash
curl -X POST http://127.0.0.1:8000/api/improve \
  -H "Content-Type: application/json" \
  -d '{
        "content": "We just shipped our biggest update yet. Latency is down 60%.",
        "platform": "linkedin",
        "analysis": { "...the analysis object from /api/analyze..." },
        "instruction": "make it punchier"
      }'
```

| Field | Required | Notes |
|---|---|---|
| `content` | yes | The original extracted text. Silently truncated at `AI_MAX_INPUT_CHARS`, never rejected for length. |
| `platform` | yes | One of `linkedin`, `instagram`, `x`, `facebook`. |
| `analysis` | yes | The exact `analysis` object `/api/analyze` returned for this content. Its `weaknesses`/`suggestions` ground what gets fixed. |
| `instruction` | no | Free-text steer, e.g. "make it shorter". Capped at 500 characters. |

**200:**

```json
{
  "success": true,
  "platform": "linkedin",
  "improved": {
    "hook": "We cut latency by 60% -- with zero downtime.",
    "body": "Six months of work went into rebuilding the ingestion layer from scratch.",
    "cta": "What's the trickiest migration you've shipped?",
    "hashtags": ["engineering", "backend"],
    "fullPost": "We cut latency by 60% -- with zero downtime.\n\nSix months of work went into rebuilding the ingestion layer from scratch.\n\nWhat's the trickiest migration you've shipped?\n\n#engineering #backend"
  }
}
```

Each platform gets genuinely different generation guidance (length, tone,
hashtag conventions) baked into the prompt — a LinkedIn and an X version of
the same post are expected to differ in structure, not just in hashtag count.

The model is instructed to preserve meaning and never invent facts not present
in the original content. This is enforced through the prompt, not verified
computationally — there is no reliable automated check for "no new facts were
added" against arbitrary text, so treat it as a strong constraint on the
model's behaviour rather than a guarantee.

---

## Errors

Every failure returns the same envelope:

```json
{
  "success": false,
  "error": { "code": "NO_TEXT_FOUND", "message": "...", "hint": "..." }
}
```

| Code | Status | Cause |
|---|---|---|
| `BAD_REQUEST` | 400 | Malformed request, missing `file` field |
| `EMPTY_FILE` | 400 | Zero-byte upload |
| `FILE_TOO_LARGE` | 413 | Exceeds `MAX_FILE_SIZE_MB` |
| `UNSUPPORTED_FILE_TYPE` | 415 | Magic bytes are not PDF/PNG/JPEG |
| `CORRUPTED_FILE` | 422 | File cannot be opened |
| `PASSWORD_PROTECTED` | 422 | Encrypted PDF |
| `NO_TEXT_FOUND` | 422 | Parsed fine, but contains no readable text |
| `OCR_UNAVAILABLE` | 503 | Tesseract binary missing |
| `AI_UNAVAILABLE` | 503 | No `GEMINI_API_KEY` configured, or the AI API is unreachable/erroring |
| `AI_RESPONSE_INVALID` | 502 | The AI answered, but its response could not be validated after a retry |
| `SERVER_ERROR` | 500 | Unexpected — logged with a traceback, never exposed |

---

## Architecture

```
app/
├── main.py            app creation, CORS, routers, exception handlers
├── config.py          all environment access, read once
├── api/               HTTP only — thin handlers, no logic
│   ├── health.py
│   ├── upload.py            extraction only
│   ├── analyze.py           extraction + AI analysis, combined
│   └── improve.py           JSON body: rewrite a post for one platform
├── services/          business logic, no HTTP knowledge
│   ├── file_service.py        orchestrates one upload
│   ├── pdf_service.py         PyMuPDF extraction + scan detection
│   ├── ocr_service.py         Pillow pre-processing + Tesseract
│   ├── analysis_service.py    Gemini call, validation, retry, error mapping
│   └── improvement_service.py same pattern as analysis_service.py, for rewrites
├── schemas/
│   ├── analysis.py       public, camelCase request/response models
│   ├── ai_analysis.py    the AI-facing contract for engagement analysis
│   └── ai_improvement.py the AI-facing contract for "Improve My Post"
└── utils/
    ├── file_validation.py   size, magic bytes, filename sanitising
    └── errors.py            the error vocabulary
```

Routes never contain logic; services never import FastAPI. That separation is
what lets the extractors — and the AI service — be tested without HTTP.

### How AI analysis works

`analysis_service.analyze_text(text)`:

1. `is_available()` — is `GEMINI_API_KEY` set? If not, fail immediately with
   `503 AI_UNAVAILABLE`. No network call is attempted.
2. Truncate the text to `AI_MAX_INPUT_CHARS`.
3. Call Gemini with `response_mime_type="application/json"` and
   `response_schema=AIAnalysisResult` — the model is constrained to emit JSON
   matching that Pydantic model's shape.
4. Validate the raw response with `AIAnalysisResult.model_validate_json()`.
   This is the real gate; the schema hint in step 3 is best-effort, not a
   guarantee. On failure, retry once with the validation error appended to the
   prompt. Fail twice → `502 AI_RESPONSE_INVALID`.
5. Map the validated, snake_case AI result onto the public, camelCase
   `ContentAnalysis` model, assigning stable `id`s for list rendering. The
   model is never asked to invent ids itself.

Every exception from the Gemini SDK (`ClientError`, `ServerError`, timeout, or
anything unexpected) is caught in one place and becomes `503 AI_UNAVAILABLE`.
The real exception is logged with `logger.exception`; the client never sees it.

### How "Improve My Post" works

`improvement_service.generate_improved_post(content, platform, analysis, instruction)`
follows the identical five-step pattern above, targeting `AIImprovedPost`
instead. The one difference is what goes into the prompt: the post's
`weaknesses` and `suggestions` from the supplied `analysis` are folded in as
grounding, so generation targets known problems rather than rewriting freely,
and platform-specific guidance (length, tone, hashtag convention) is added
based on the selected `platform` — this is what makes a LinkedIn rewrite and
an X rewrite of the same post genuinely differ, not just swap hashtags.

`improvement_service.py` intentionally does **not** import from
`analysis_service.py`, even though both maintain an near-identical ~10-line
"is a key configured, get me the Gemini client" block. This is accepted,
contained duplication rather than a shared module, so that building this
feature never risks the already-tested internals of `analysis_service.py`. A
reasonable follow-up if the two features are developed further together.

### Security notes

- **Nothing is written to disk.** PyMuPDF opens PDFs from a byte stream and
  Pillow decodes images from a `BytesIO` buffer, so there is no temp-file
  cleanup to get wrong, no path traversal, and nothing on disk that could be
  executed. Uploaded bytes are only ever parsed as data.
- **Type is decided by magic bytes**, not by extension or `Content-Type`. Both
  of those are attacker-controlled.
- **Size is enforced while streaming**, in 64 KB chunks, so a hostile 2 GB body
  is rejected after ~10 MB rather than being buffered first.
- **Filenames are reduced to a basename** before being echoed back or logged.
- **DoS guards:** OCR page cap (`MAX_OCR_PAGES`) and a Pillow decompression-bomb
  limit (~64 MP).
- **No stack traces leave the process.** The catch-all handler logs the real
  exception and returns a generic message.
- **CORS is an explicit allowlist**, never `*`. See the comment in `main.py`.
- **`GEMINI_API_KEY` is backend-only.** Read once in `config.py`, used only to
  construct the Gemini client, never included in any response body, error
  message, or the `/openapi.json` schema. Covered by a dedicated regression
  test (`TestKeyNeverLeaks`) rather than left as an informal guarantee.
- **Only extracted text reaches the AI**, truncated to `AI_MAX_INPUT_CHARS`. No
  filename, IP address, or request metadata is included in the prompt.

---

## Deployment note

Tesseract is a system binary, so a plain Python host will not have it. Deploy
with a Dockerfile that runs `apt-get install -y tesseract-ocr`, otherwise every
image upload returns `503` in production while working perfectly on your laptop.
