# ADR-0012: Separate "alert" (every AI detection) from "case" (manually tracked)

**Status**: Accepted

## Context

ADR-0011 gave `Violation` a `status`/`assigned_to`/notes workflow and a
Case Violation page listing every `Violation` row as a "case." In
practice, `apps/inference` re-emits a detection every time its
`COOLDOWN_SECONDS` (60s default) elapses for an ongoing condition — the
same non-compliant Workshop photo, say — so Case Violation filled up with
dozens of near-identical "Baru" entries a few dozen seconds apart, each a
separate unassigned "case." That's not a case management workflow, it's
the raw detection log wearing a case management UI.

## Decision

`Violation` gains `is_case: bool` (default `False`). Every AI detection
still creates a `Violation` row exactly as before — nothing changes in
`apps/inference` or `POST /api/events` — but it now starts life as a
plain **alert**, not a case:

- **Alerts**: the full, unfiltered detection log. APD Detection/Vehicle
  Detection's "Riwayat Pelanggaran" tables show these (`GET
  /api/violations` with no `is_case` filter) — every row visible, tagged
  with a muted "Alert" badge if not (yet) a case.
- **Cases**: an alert a human explicitly promoted (`PUT
  /api/violations/{id}/case {"is_case": true}`) because it actually
  warrants tracking. Case Violation only lists these (`is_case=true`).
  Only promoted rows get the status stepper, assignment, and notes UI in
  the shared `case-modal.js` — an unpromoted alert's detail view is just
  the snapshot/metadata plus one button, "Jadikan Kasus Investigasi."
- Un-promoting (`is_case: false`) is symmetric and available from the
  same modal ("Batalkan status kasus") — it only flips the flag, it does
  not delete the underlying detection or its notes, so nothing is lost if
  someone reverses a promotion made by mistake.
- No role restriction on promoting/un-promoting: this is a judgment call
  any authenticated user (Operator included) makes about what they're
  watching, distinct from assign/close, which stay Supervisor/Admin-only
  per ADR-0011's matrix.

`GET /api/reports/summary` now reports two families of numbers:
alert-level (`total`, `apd_total`, `vehicle_total`, the daily trend and
per-camera ranking — "how much is happening," counting every detection)
and case-level (`case_total`, `completed_count`/`completion_rate`,
`avg_response_minutes` — "how well are we handling what we chose to
track," scoped to `is_case=true` rows only, since status/response-time
isn't meaningful for something nobody decided to act on). `GET
/api/stats`'s `open_cases` (Dashboard's "Kasus Terbuka" tile) is likewise
`is_case=true AND status != 'selesai'`, not "every unacknowledged alert."

## Consequences

- Case Violation stays small and meaningful regardless of how often
  `apps/inference` re-fires on an ongoing condition — volume lives in the
  alert log (APD/Vehicle Detection), not in case management.
- One more manual step (promote) stands between "AI saw something" and
  "it's a tracked case" — deliberate, not an oversight: this is exactly
  the gap the user flagged (raw detections were auto-becoming cases with
  no human decision in between).
- `is_case`'s migration (`ALTER TABLE violations ADD COLUMN IF NOT
  EXISTS is_case BOOLEAN NOT NULL DEFAULT FALSE`) means every violation
  already in the database from before this change is treated as a plain
  alert, not a case, on upgrade — anything that was being tracked as a
  "case" under the old all-rows-are-cases model needs re-promoting by
  hand if it still matters.
