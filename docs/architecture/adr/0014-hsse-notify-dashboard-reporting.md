# ADR-0014: HSSE Direct Notify, Executive Dashboard, and comprehensive Recurring Report

**Status**: Accepted

## Context

The user shared three requirement cards from an external HSSE planning
document and asked for the app's Notifications, Dashboard, and Reports
to be brought in line with them:

- **Direct Notify**: "Setiap pelanggaran yang terdeteksi langsung
  dikirim ke saluran resmi tim HSSE, lengkap dengan waktu, lokasi, dan
  bukti gambarnya."
- **Executive Dashboard**: "Tren pelanggaran mingguan, area dengan
  pelanggaran terbanyak, tingkat kepatuhan per area, serta status
  pencapaian target HSSE."
- **Recurring Report**: "Laporan dibuat dan dikirim otomatis melalui
  email resmi kepada HSE Officer dan manajemen, tanpa perlu disusun
  manual."

Direct Notify (email-on-violation) and the Dashboard/Reports pages
already existed (ADR-0011, ADR-0012) but fell short of these three
specs in concrete ways: the alert email carried no photo evidence, the
Dashboard had no trend/top-location/compliance view, and there was no
automatic recurring report at all — "Unduh Laporan" on the Reports page
wasn't wired to anything real, either.

The user separately confirmed the mail transport itself should stay
generic: *"sbenrnya kalau SMTP nya saya rasa bebas ya, yang penting dia
kirim ke outlook perusahaan mereka. karena gak tau juga mereka pake
smtp apa"* — i.e. don't build anything Outlook/Graph-API-specific now,
since which SMTP relay the company will actually point this at isn't
known yet.

## Decision

**HSSE compliance target — one source of truth.** `NotificationRule`
(already one row per category, ADR-0011) gains `weekly_target: int` —
the max violations that category should see in a rolling 7-day window.
`GET /api/reports/summary` computes a new `compliance: list[...]` field
from it: `violations_7d`, `weekly_target`, `compliance_pct = clamp(1 -
violations_7d/weekly_target, 0, 1)`, `target_met`. This is *always* a
rolling last-7-days figure regardless of the `?days=` query param — a
weekly target stays the yardstick even when viewing a 30-day trend.
Both the Executive Dashboard and Laporan & Analitik render this same
field, so "tingkat kepatuhan" can never drift between the two pages.
`weekly_target` is editable from Pengaturan > Aturan Notifikasi, right
next to the confidence/escalation fields it already had.

**Direct Notify gets photo evidence.** `send_notification()` in
`notifications.py` now accepts the raw snapshot bytes `ingest_event()`
already decodes and writes to disk, and attaches them to the alert
email as `MIMEImage` (falls back to a plain-text email when a
violation has no snapshot). Time, location, and confidence were already
in the body from ADR-0011 — this closes the one gap ("bukti gambarnya")
against the spec.

**Executive Dashboard** (`index.html`) gains three sections sourced
from the same `_compute_report_summary()` helper `/api/reports/summary`
already used: a weekly trend bar chart (the same SVG builder as Laporan
& Analitik's, so the two pages speak one visual language), an "Area
dengan Pelanggaran Terbanyak" table (top 5 of the existing `by_camera`
ranking), and a "Kepatuhan & Target HSSE" panel rendering the new
`compliance` field with a Tercapai/Melebihi Target badge per category.

**Recurring Report** is a new `ReportSchedule` singleton table (`id=1`:
`enabled`, `frequency_days`, `recipient_email`, `last_sent_at`), backed
by a periodic asyncio task (`_periodic_recurring_report_check`, checked
every 10 minutes) matching the existing `_periodic_escalation_check`
pattern (ADR-0011). When due, it calls `_compute_report_summary()` and
a new `send_recurring_report()` that formats the same numbers the
Dashboard/Reports pages show into a plain-text HSSE summary email —
never a hand-compiled report. `GET`/`PUT /api/report-schedule`
(admin-only) configure it from Pengaturan > Notifikasi Email, alongside
a `POST /api/report-schedule/send-now` "Kirim Sekarang" button so the
automation can be demonstrated on demand instead of waiting out
`frequency_days`.

**Comprehensive report export.** `GET /api/reports/export?kind=...`
returns CSV (zero new dependencies, opens directly in Excel): `kind=
executive` is the compact KPI + compliance + top-locations sheet a
manager forwards as-is; `kind=detail` (default) is every violation row
in the window, one line each, for real casework. Same auth pattern as
the snapshot endpoint (ADR-0011/ADR-0012 fixes): accepts `?token=`
alongside the `Authorization` header, since a plain `<a href download>`
can't attach a header — Laporan & Analitik's two "Unduh Laporan"
buttons build that URL and click a throwaway anchor.

**SMTP stays deliberately generic.** No Outlook/Graph-API-specific code
was added. `notifications.py`'s `SMTP_HOST`/`PORT`/`USER`/`PASSWORD`/
`USE_TLS` env vars already point at any relay that accepts normal SMTP
submission — including a corporate Outlook/M365 relay, if that's what
Pertamina EP designates once it's decided. This is an intentional scope
cut, not an oversight: if a given M365 tenant turns out to have legacy
SMTP AUTH disabled, that specific tenant would need OAuth2 (Microsoft
Graph API) instead — a different, larger piece of work not worth
building speculatively against an unconfirmed target.

## Consequences

- Compliance math lives in exactly one place
  (`main.py::_compute_report_summary`), consumed by the Dashboard, the
  Reports page, both CSV exports, and the recurring-report email —
  changing `weekly_target` or the compliance formula can't leave one of
  those five surfaces showing a different number than the rest.
- The recurring report is real automation (a live asyncio task that
  actually fires and sends mail), but on the same honest-gap footing as
  ADR-0011's escalation email: one shared `recipient_email`/
  `NOTIFY_EMAIL_TO`, not a real per-person HSE Officer/management
  distribution list.
- `notification_rules.weekly_target` migration (`ALTER TABLE ... ADD
  COLUMN IF NOT EXISTS weekly_target INTEGER NOT NULL DEFAULT 100`) and
  the new `report_schedule` table both apply in place — no volume drop
  needed to upgrade.
- Whichever SMTP relay Pertamina EP eventually designates (Outlook/M365
  or otherwise), pointing this deploy at it is purely an env-var change
  in `.env` — unless that tenant requires OAuth2-only submission, which
  would need new code, deliberately not built ahead of a confirmed
  target.
