# postpilot.ai — Frontend

**Create. Optimize. Engage.**

Upload a social media post as a PDF or an image. postpilot.ai extracts the text,
scores how likely the post is to earn engagement, and tells you exactly what to
change.

This package is the **frontend only**. It talks to a FastAPI backend over a
single HTTP endpoint and contains no extraction, OCR or scoring logic of its own.

---

## Live links

| | URL |
|---|---|
| Application | _add after deploying_ |
| API | _add after deploying_ |

---

## Tech stack

| Choice | Why |
|---|---|
| **Next.js 16 (App Router)** | Server Components keep the marketing shell at zero JavaScript; only the interactive analyzer hydrates. |
| **React 19** | Required by Next 16. |
| **TypeScript (strict)** | The API contract is defined as types first, so a backend field change is a compile error rather than a runtime surprise. |
| **Tailwind CSS v4** | CSS-first config; design tokens live in `app/globals.css` and generate the utilities. |
| **shadcn/ui** | Components are copied into the repo, not imported from a package, so they can be edited freely. Only 7 primitives are used. |
| **lucide-react** | Icon set used by shadcn/ui. |

Runtime dependencies total 10 packages. There is no state library, no data-fetching
library and no chart library — the score ring is hand-drawn SVG.

---

## Getting started

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000

### Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | **Yes** | none | Base URL of the FastAPI backend, no trailing slash. |
| `NEXT_PUBLIC_MAX_FILE_SIZE_MB` | No | `10` | Client-side upload guardrail. Must match the backend limit. |

`NEXT_PUBLIC_API_URL` deliberately has **no fallback**. A hardcoded localhost
default would work in development and then fail confusingly in production; an
empty value surfaces as an explicit configuration error instead.

> `NEXT_PUBLIC_*` values are inlined at **build** time. Changing one on your
> host requires a redeploy to take effect.

### Scripts

```bash
npm run dev        # dev server
npm run build      # production build
npm run start      # serve the production build
npm run typecheck  # tsc --noEmit
```

---

## The API contract

The frontend calls exactly one endpoint.

```
POST {NEXT_PUBLIC_API_URL}/api/analyze
Content-Type: multipart/form-data
Body: file=<the PDF or image>
```

`multipart/form-data` is used rather than JSON because the payload is binary.
Base64-encoding a PDF into a JSON string would inflate it by about a third for
no benefit.

**Success — `200`:** the full `AnalyzeResponse` shape defined in
[`types/analysis.ts`](./types/analysis.ts). That file is the single source of
truth; the backend must satisfy it.

**Failure — `4xx` / `5xx`:**

```json
{
  "success": false,
  "error": { "code": "NO_TEXT_FOUND", "message": "...", "hint": "..." }
}
```

Recognised codes: `BAD_REQUEST`, `UNSUPPORTED_FILE_TYPE`, `FILE_TOO_LARGE`,
`EMPTY_FILE`, `NO_TEXT_FOUND`, `CORRUPTED_FILE`, `PASSWORD_PROTECTED`,
`SERVER_ERROR`. Anything else is normalised by HTTP status.

The backend must send CORS headers permitting the frontend origin, and answer
the browser's `OPTIONS` preflight.

---

## Architecture

```
app/layout.tsx          Server Component — shell, fonts, header, footer
  └── app/page.tsx      Server Component — hero + feature strip (zero JS)
        └── components/analyzer.tsx   ◄── the only meaningful client boundary
              │
              ├── hooks/use-analyzer.ts     state machine (useReducer)
              │     ├── lib/validate-file.ts
              │     └── lib/api.ts          the only file that calls fetch()
              │           ├── lib/config.ts    all env access, read once
              │           └── lib/errors.ts    the AppError vocabulary
              │
              └── one of four screens, chosen by `status`
```

### State

One `useReducer`, five states, no state library:

```
idle → selected → analyzing → success
          ▲          │  │
          │          │  └─ cancel ─→ selected
          └─ retry ─ error ─ reset ─→ idle
```

Modelling this as a finite set of states rather than several booleans makes
invalid combinations impossible to represent — you cannot get a spinner beside
an error, or a stale result under a new upload.

### Key decisions

- **One API file.** `lib/api.ts` is the only module that knows the backend
  exists. It knows a URL and two payload shapes, nothing about Python, OCR or
  Tesseract.
- **Errors are a vocabulary, not strings.** Every failure becomes an `AppError`
  with a stable code, a human message and an optional hint, so error copy lives
  where the error is created.
- **Runtime response validation.** TypeScript types vanish at build time, so
  `isAnalyzeResponse()` checks every branch the UI reads. A malformed payload
  becomes a handled error instead of a crash.
- **No mock data.** The app shows real results or a real error. It never
  fabricates analysis.
- **Colour tokens meet WCAG AA.** `--success` and `--warning` are darker than a
  typical brand palette because they are used for text; both were measured at
  above 4.5:1 in light and dark mode.
- **Dark mode follows the OS.** Driven purely by `prefers-color-scheme`, so
  there is no theme state, no hydration mismatch and no wrong-theme flash.

---

## Accessibility

- Skip link to main content
- One tab stop per control; the file input is hidden from the tab order and the
  accessibility tree, and the visible button is the real control
- Errors announced via `role="alert"`
- Loading status in a scoped `role="status"` live region; skeletons are
  `aria-hidden`
- Focus moves to the results heading when analysis completes
- All colour pairs meet WCAG AA (4.5:1) in both themes
- `prefers-reduced-motion` respected

---

## Known limitations

- Analysis requires the backend; there is no offline or demo mode by design.
- Scoring is heuristic, based on published social media best practice, not on a
  trained model or platform data.
- OCR accuracy depends on scan quality. Low-confidence results are flagged in
  the UI.
- A free-tier backend may cold-start; the UI shows a hint after 10 seconds and
  gives up at 90.
