# ADR-0011: Backport the design-canvas IA and 3-role RBAC into the real app

**Status**: Accepted

## Context

The design-canvas mockup (a separate, pre-code visual review artifact —
see the product decision log, not tracked as an ADR since it produced no
running code) went through several rounds of user-driven iteration and
landed on:

- A restructured information architecture: per-category pages (APD
  Detection, Vehicle Violation) instead of a generic "Live Streaming"
  tab, plus new Case Violation and Laporan & Analitik pages.
- A light, bright visual theme (replacing an earlier dark one) — including
  the login screen.
- A three-role access model — **Admin** (users, cameras, notification
  rules), **Supervisor** (assign and close cases), **Operator** (monitor
  and acknowledge, cannot assign/close/change settings) — instead of the
  original two (operator/admin).

None of this had been carried into the actual running application
(`apps/frontend`, `infra/keycloak`), which still had the old dark login
theme and the old two-page IA. This ADR is the "and now build it for
real" step: not just repainting the frontend, but making the RBAC and
case-management workflow the mockup implied actually work end to end.

## Decision

### 1. Real information architecture

`apps/frontend` is now six real pages sharing one layout (`shell.js`
renders the header/sidebar from the logged-in user's actual token — no
"preview as" switcher like the mockup needed, since production just
shows what the real role is):

`index.html` (Dashboard) · `apd.html` · `vehicle.html` · `cases.html` ·
`reports.html` · `settings.html` (+ `admin.html`, unchanged position as
a separate portal). `case-modal.js` is one shared "Case Detail" modal
used by apd/vehicle/cases instead of three copies.

### 2. Three real realm roles, enforced server-side

Added `supervisor` to `infra/keycloak/import/realm-visionguard.json`
plus a demo user (`ahmad.fauzi` — same name used as a case assignee in
earlier mockup data, kept for continuity). `apps/backend/app/auth.py`
gained `get_current_manager` (admin OR supervisor). Enforcement lives on
the backend, not just hidden UI:

| Action | Operator | Supervisor | Admin |
|---|---|---|---|
| View all pages except Pengaturan | yes | yes | yes |
| Move a case Baru -> Diproses | yes | yes | yes |
| Assign a case / move to Selesai | **no (403)** | yes | yes |
| Camera CRUD, Pengaturan page | **no (403 / hidden)** | **no (403 / hidden)** | yes |

`settings.html` also renders an "Akses Terbatas" notice for non-admin —
consistent with the earlier finding that hiding a nav item is not
access control; both layers exist here.

### 3. Real case-management data model, not just a status flag

`Violation` gained `status` (baru/diproses/selesai), `assigned_to`, and
a `notes` child table (`ViolationNote`) — the mockup's Case Violation
page needed all three and none existed in the real schema before this.
`acknowledged` (the older boolean) is kept and kept in sync for
backward compatibility rather than removed.

### 4. A real reporting endpoint, not mockup numbers

The mockup's Laporan & Analitik page used hand-picked illustrative
numbers. `GET /api/reports/summary` computes the same shape (category
split, daily trend, per-camera ranking, completion rate, average
response time) from real `Violation` rows — `reports.html` renders
whatever that endpoint actually returns, including "no data yet" for a
fresh deploy. `responded_at` (new column) is set the first time a case
leaves 'baru', which is what "average response time" measures.

### 5. Notification rules are now real, persisted config

`NotificationRule` (new table, one row per category) backs the
Pengaturan > Aturan Notifikasi tab: `min_confidence`,
`escalate_after_minutes`, `escalate_enabled`, `email_enabled`.
`apps/inference` polls `GET /internal/notification-rules` (30s cache)
so changing the threshold in the dashboard changes live detection
sensitivity, not just a number in a form — see the inference module's
own docstring update. A real `_periodic_escalation_check` (backend,
every 60s) sends an escalation email once a 'baru' case exceeds its
category's `escalate_after_minutes`, honestly short of true per-role
routing since there's still only one configured inbox
(`NOTIFY_EMAIL_TO`) — the email's subject/body say who it's *meant* for.

### 6. Login theme repainted to the approved light palette

`infra/keycloak/themes/pertaminaep/login/` (`login.css`, `template.ftl`)
now matches the canvas's light green/white split-screen design (was a
dark red/near-black theme). Also enabled Indonesian
(`internationalizationEnabled` + `defaultLocale: "id"`) so Keycloak's
own bundled message text ("Sign in to your account", etc.) renders in
Indonesian too, consistent with the rest of the app, without hand
overriding every message key.

### 7. Vendored `hls.js` instead of a CDN — and fixed a real latent bug

While rebuilding the camera-tile pages, found that the pre-existing
`attachStream()` referenced `window.Hls` but no page ever loaded an
`Hls` implementation from anywhere — live video only ever worked in a
browser with native HLS support (Safari), never Chrome. Fixed by
vendoring `hls.js` 1.5.15 as a local file (`apps/frontend/hls.min.js`,
committed, no CDN) rather than reintroducing an external dependency —
consistent with this project's existing anti-CDN stance for
offline/on-prem resilience (the same reasoning `apps/frontend/auth.js`'s
pure-JS SHA-256 fallback documents).

## Consequences

- Three logins now genuinely behave differently: what you can see, what
  buttons are enabled, and what the backend will actually let you do all
  follow the same role, checked in one place (`auth.py`) rather than
  duplicated per endpoint.
- `Violation.category` was silently renamed from `"safety"` to `"apd"`
  as part of this (see `_run_schema_migrations`'s one-time `UPDATE`) to
  match `Camera.category` and the rest of the UI's terminology — anyone
  querying the API by the old string needs to update it.
- The escalation email and the notification-rule confidence threshold
  are real, but still share the single `NOTIFY_EMAIL_TO` inbox and the
  same two pretrained models from ADR-0010 — this ADR did not add
  per-role email routing or new detection capability, only the platform
  scaffolding a real version of either would plug into.
- `apps/frontend` no longer has a build step, a framework, or a router —
  six plain HTML pages sharing `styles.css`/`auth.js`/`shell.js`. This
  matches the project's existing "vanilla JS, no build step" choice
  rather than introducing one now; revisit if the page count grows much
  further.
