# ADR-0015: Comprehensive PDF reports with charts and photo evidence

**Status**: Accepted

## Context

ADR-0014 shipped "Unduh Laporan" as plain CSV. The user's reaction was
direct: *"jelek amat report nya jadi csv pake pdf yang comprehensif ada
gambar dan detail"* — a CSV has no branding, no charts, and can't carry
photo evidence, so it read as a raw data dump rather than a report a
manager or HSE Officer would actually forward.

## Decision

`GET /api/reports/export` now returns a real PDF, built by a new
`apps/backend/app/pdf_report.py` using **reportlab** (+ Pillow for image
handling) — chosen over alternatives like WeasyPrint specifically
because it's pure-Python/wheel-only: no apt-get native libs (pango,
cairo, ...) need adding to the already-minimal `python:3.12-slim`
backend image, just two more `pip install` lines.

Both `kind`s share one Pertamina EP–branded letterhead (logo + the
app's own brand-gradient strip, same color tokens as `styles.css`) and
the same sections `_compute_report_summary()` already feeds the
Dashboard/Reports pages with — so a PDF number can never drift from
what the UI shows:

- **`kind=executive`**: KPI table, Kepatuhan & Target HSSE table
  (color-coded Tercapai/Melebihi Target, same as the Dashboard badge),
  a real bar chart of the weekly trend (reportlab's
  `VerticalBarChart`, not just a table of numbers), and a top-10
  locations table. One-to-two pages, meant to be forwarded as-is.
- **`kind=detail`**: everything above, plus a full violation table
  (capped at `MAX_EXPORT_DETAIL_ROWS = 500`, most recent first, to keep
  generation time and file size sane against a busy demo window) and a
  **photo-evidence gallery** — up to 12 of the period's actual snapshot
  JPEGs read straight off `SNAPSHOT_DIR`, laid out 3-per-row with a
  timestamp/camera/confidence caption under each. This is the literal
  "ada gambar" the CSV never had.

**The Recurring Report email also gained a PDF.** `send_recurring_report`
(ADR-0014) now accepts `pdf_bytes` and attaches it via a generalized
`_send_email(..., attachments=[(filename, bytes, mime_type), ...])` —
the same mechanism Direct Notify's snapshot attachment was refactored
onto. `_run_recurring_report_check` and the `send-now` manual trigger
both build an `executive`-kind PDF (not `detail`, to keep the automatic
email a reasonable size) and attach it, so the automated email carries
a real formatted report, not just a plain-text wall of numbers.

## Consequences

- Two new backend dependencies (`reportlab`, `Pillow`) — both
  pure-Python wheels, no Dockerfile changes needed beyond
  `requirements.txt`.
- `apps/backend/app/assets/pertamina-ep-logo.jpg` is a backend-local
  copy of the frontend's logo — the PDF generator runs server-side and
  has no access to the frontend's static files, so the asset had to be
  duplicated rather than referenced.
- `kind=detail`'s 500-row cap and 12-photo cap are deliberate: this
  report can be requested over a 30+ day window, which the demo dataset
  alone can put at 1,800+ violations — generating a PDF (and gallery)
  for every single one would be slow and enormous. The UI note on the
  detail table page states the cap explicitly rather than silently
  truncating.
- The CSV endpoints/format are gone entirely, not kept as a `?format=`
  option — the user's ask was to replace the CSV, not add PDF beside
  it.
