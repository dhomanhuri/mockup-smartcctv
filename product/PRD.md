# Product Requirements Document — Smart CCTV AI

Companion to [BRD.md](BRD.md) (the why) and
[HLD.md](../docs/architecture/HLD.md) (the how). This is the what:
features, requirements, acceptance criteria — reflecting what the current
demo/POC actually implements, with gaps called out explicitly rather than
glossed over.

## 1. Personas

- **Operator** — watches the dashboard during a shift, reviews and
  acknowledges violations, can add cameras. Keycloak role: `operator`.
- **Platform Admin** — everything an Operator can do, plus manages who
  else has an account. Keycloak role: `admin` (a superset of `operator`).

## 2. Features

### F1 — Camera management (CRUD)
Add a camera with just a name, IP, and optional location/RTSP URL. Edit
or remove any camera later; removing one also removes its violation
history. **Status: implemented** (`Kelola Kamera` page,
`/api/cameras/*`).

### F2 — Live streaming
Watch a live view of any camera that has an RTSP URL, rendered as HLS in
the browser. Cameras without a stream show "no signal" rather than
erroring. **Status: implemented** for cameras with a reachable RTSP
source; the demo ships one synthetic source to prove the path end to end
(see [ADR-0005](../docs/architecture/adr/0005-mediamtx-for-streaming.md)).

### F3 — Violation detection & review
Every detected violation is stored with type, camera, confidence,
severity, and timestamp; appears instantly in a live feed and in a
filterable history table; can be marked acknowledged. **Status:
implemented**, now running **real pretrained-model inference** (two
YOLOv8-nano models, no training done) rather than the earlier simulator —
see [ADR-0010](../docs/architecture/adr/0010-real-pretrained-inference.md)
(and [ADR-0003](../docs/architecture/adr/0003-simulated-inference.md) for
the original simulated milestone this replaced). Two violation types ship
today: no-helmet (real detection) and truck-bed-riding (real person
detection + a zone heuristic — no pretrained model exists for the
specific behavior); the schema (`VIOLATION_META`) is built to add more
without a migration.

### F4 — Email alerting
Every new violation sends an email with type/camera/confidence/severity.
**Status: implemented**, pointed at a demo SMTP catcher — corporate SMTP
is a config change (`.env`), not a code change.

### F5 — Authentication & role separation
Dashboard access requires login (Keycloak SSO, PKCE). A separate Admin
Dashboard, gated by role, lets an admin create/enable/disable user
accounts without touching Keycloak's own console. **Status:
implemented**, now with **three** realm roles (Operator, Supervisor,
Admin) instead of two, enforced on the backend not just the UI — see
[ADR-0001](../docs/architecture/adr/0001-single-realm-rbac.md),
[ADR-0006](../docs/architecture/adr/0006-service-account-for-admin-api.md),
and [ADR-0011](../docs/architecture/adr/0011-real-app-ia-and-rbac-backport.md)
for the RBAC matrix.

### F6 — Reporting & analytics
Periodic (daily/weekly) violation trend reports, exportable. **Status:
mostly implemented** — `GET /api/reports/summary` (Laporan & Analitik
page) computes category split, daily trend, per-camera ranking,
completion rate, and average response time over a selectable 7/30-day
window, from real `Violation` rows. Still missing: export (CSV/PDF) and
scheduled/emailed periodic reports — see
[ADR-0011](../docs/architecture/adr/0011-real-app-ia-and-rbac-backport.md).

### F7 — Object storage for evidence (snapshot/video clip)
Store a snapshot or short clip alongside each violation as evidence.
**Status: partially implemented.** Real inference now produces an actual
frame at detection time, so `apps/inference` sends it and `backend` saves
it to a `snapshots` named volume (`Violation.snapshot_ref`), servable via
`GET /api/violations/{id}/snapshot` and shown as a "Lihat snapshot" link
in the dashboard — see [ADR-0010](../docs/architecture/adr/0010-real-pretrained-inference.md).
Still open: no real object storage (e.g. MinIO/S3) for multi-host
durability, no short-clip capture (snapshot only), and no retention/
pruning policy — see [roadmap.md](roadmap.md).

### F8 — Case management workflow (Case Violation page)
Track a violation through Baru → Diproses → Selesai, assign it to a
named person, and keep an investigation note trail. **Status:
implemented** — `Violation.status`/`assigned_to` + the new
`ViolationNote` table, with Supervisor/Admin required to assign or close
a case (Operator can only acknowledge) — enforced on the backend, see
[ADR-0011](../docs/architecture/adr/0011-real-app-ia-and-rbac-backport.md).
`assigned_to` is a free-text name today, not a link to a real user
account — good enough for this scale, would need a real directory to
scale further.

## 3. Non-functional requirements

- **Auth**: every dashboard-facing endpoint requires a valid token;
  admin-only endpoints additionally require the `admin` realm role, and
  case-management actions (assign, close) require `admin` or
  `supervisor` — see [ADR-0011](../docs/architecture/adr/0011-real-app-ia-and-rbac-backport.md).
  PKCE must work over plain HTTP as well as HTTPS (see the
  `crypto.subtle` note in [troubleshooting.md](../docs/runbook/troubleshooting.md)) —
  this on-prem deployment doesn't assume TLS is available yet.
- **Resilience**: losing a non-database service (MediaMTX, Mailpit)
  should not lose data, and streaming should self-heal without manual
  intervention — see the persistence notes in
  [HLD.md](../docs/architecture/HLD.md).
- **Onboarding**: adding a camera must require nothing beyond
  name/IP/(optional RTSP URL/location) — no separate provisioning step.
- **Observability (minimum)**: an operator must always be able to tell,
  at a glance, which cameras are live vs. have no signal, and which
  violations are unacknowledged.

## 4. Explicitly out of scope (this iteration)

- Model **training** — real inference now runs existing pretrained
  models unmodified (see [ADR-0010](../docs/architecture/adr/0010-real-pretrained-inference.md)),
  but fine-tuning or training a custom model (e.g. a real "truck-bed
  rider" classifier) is still out of scope.
- Per-camera fine-grained permissions (e.g. "operator can only see
  cameras at Site X") — role-level permissions (Operator/Supervisor/
  Admin) are now implemented; scoping *within* a role by camera/site is
  not (see [ADR-0011](../docs/architecture/adr/0011-real-app-ia-and-rbac-backport.md)).
- Multi-site / multi-edge-server aggregation (single on-prem server for
  now — see the phasing in [roadmap.md](roadmap.md)).
- TLS/HTTPS termination.

## 5. Sample acceptance criteria

- *Given* an operator with a valid session, *when* they submit "+ Tambah
  Kamera" with a name and IP only, *then* the camera appears in both
  "Live Streaming" (as "no signal") and "Kelola Kamera" immediately,
  with no page reload required elsewhere in the app to pick it up next
  load.
- *Given* a camera with a valid RTSP URL, *when* a violation event for
  that camera is posted to `/api/events`, *then* within one WebSocket
  round-trip the Live Alert Feed shows the new entry and the camera
  tile flashes, without a manual refresh.
- *Given* a user without the `admin` role, *when* they navigate to
  `/admin.html`, *then* they see an explicit "access denied" message,
  never a silent redirect back to Keycloak login.
