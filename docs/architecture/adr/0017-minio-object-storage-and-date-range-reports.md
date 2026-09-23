# ADR-0017: MinIO object storage for snapshots, date-range reporting

**Status**: Accepted

## Context

Two related requests landed together, both about the reporting/evidence
pipeline maturing past the demo-first shortcuts it started with:

1. Violation snapshot evidence (ADR-0011/0014) was stored as plain files
   on a Docker volume owned directly by the `backend` container
   (`/data/snapshots`). Asked directly: *"berati ini belom ada object
   storagenya ya?"* — correct, and asked to fix it with an open-source
   option: *"pake minio aja yang opensource. biar report pdf nya itu ada
   bukti alertnya juga."*
2. The Reports page only ever offered two fixed presets ("7 Hari" / "30
   Hari") computed as "N days back from right now." Asked for a real
   calendar range: *"itu dibuat kyk time range gitu fitur reportingnya.
   bisa milih mo tanggal berapa maksimla bisa generate 1 bulan gitu"* —
   pick an explicit start/end date, capped at about a month.

## Decision

### MinIO for snapshot evidence

Added a `minio` service (`minio/minio`, open-source, S3-compatible) to
`infra/docker-compose.yml`, credentials from `.env`
(`MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`), console exposed on `:9091`
(same "admin UI on its own port, off port 80" pattern as Keycloak's
`:8081` and Mailpit's `:8025`) — the S3 API port itself is never
published, reachable only from the `backend` container over the docker
network.

New `apps/backend/app/storage.py` wraps the `minio` Python client with
just what this app needs: `ensure_bucket()` (called once at backend
startup, same idempotent pattern as the existing `_seed_*` functions),
`put_snapshot()`, `get_snapshot()`. `_save_snapshot()` in `main.py` now
uploads to MinIO instead of writing to local disk; `GET
/api/violations/{id}/snapshot` fetches from MinIO and streams the bytes
back rather than serving a `FileResponse` off a volume path. The
`pdf_report.py` photo gallery (ADR-0015) does the same — it now pulls
each evidence photo from MinIO instead of reading `snapshot_dir` off
disk, so **every** consumer of a snapshot (the live dashboard `<img>`,
the Direct Notify email attachment, the PDF photo gallery) goes through
the same storage layer.

The backend's own `snapshots` Docker volume is removed entirely — no
local disk fallback, no dual-write. If MinIO is down, `put_snapshot()`
logs and returns `False`; the violation still gets recorded, just
without photo evidence, matching this app's existing "degrade, don't
crash" posture (e.g. the inference worker's stale-rules fallback).

### Date-range reporting

`GET /api/reports/summary` and `GET /api/reports/export` no longer take
a `days` count; both now take explicit `start`/`end` query params
(inclusive ISO dates, e.g. `2026-08-01`), defaulting to the last 7 days
when omitted, validated by a shared `_resolve_report_range()`:
`start > end` and any span over `MAX_REPORT_RANGE_DAYS = 31` both 400.
`_compute_report_summary()` takes the resolved `(start_date, end_date)`
pair directly and zero-fills every day in that range in the `daily`
trend series (not just days that happen to have a violation) — a
user-picked range benefits from a continuous line more than the old
"however many days happened to have data" behavior did.
`ReportSummaryOut` gained `start`/`end` string fields so a report always
carries the exact period it covers, not just a day count.

The Recurring Report job (`_run_recurring_report_check`,
`send-now`) computes its window the same way — `frequency_days` back
from today, clamped to `MAX_REPORT_RANGE_DAYS` — so an admin can't
configure a recurring report wider than a single export can ever be
generated for.

**Frontend** (Laporan & Analitik): the "7 Hari / 30 Hari" pills stay as
quick-set shortcuts but sit alongside two `<input type="date">` fields
(Dari / Sampai) and a "Terapkan" button for an arbitrary range, with the
31-day cap enforced client-side too (before the request even goes out)
and again server-side (the actual guard). The trend chart's x-axis
switches from day-of-week letters to day-of-month numbers, thinning the
labels shown (every 2nd/3rd/5th) past 10/16/24 bars so a full month of
bars never overlaps — the PDF's own trend chart (`pdf_report.py`) uses
the identical thinning logic so both stay visually consistent. The
Executive Dashboard's own trend widget (`index.html`) is deliberately
left on its fixed rolling-7-day window — it's a glance, not a report a
user tailors — and just updates its own API call to the new
`start`/`end` params.

## Consequences

- Snapshot evidence is no longer tied to any one backend container's
  filesystem — a backend redeploy, scale-out, or replacement no longer
  risks losing photo evidence, and the storage layer could later point
  at a real hosted S3-compatible service with only an env-var change
  (same client library, `storage.py` untouched).
- This is another reset: existing snapshot files in the old
  `visionguard_snapshots`/`smart-cctv-ai_snapshots` volume are not
  migrated into MinIO — consistent with the demo/POC posture already
  established in ADR-0016 (this whole stack was just reset fresh
  anyway).
- `GET /api/reports/summary?days=N` and `GET /api/reports/export?days=N`
  are a breaking change (removed, not kept alongside `start`/`end`) —
  acceptable since both are internal to this app's own frontend, not a
  published API with outside consumers.
- A report spanning a full month generates a noticeably busier
  `kind=detail` PDF (more rows against the existing `MAX_EXPORT_DETAIL_ROWS
  = 500` cap, same 12-photo gallery cap from ADR-0015) — both caps
  already existed and needed no changes to stay sane at the new max
  range.
