# Roadmap

Phases from the original platform plan, annotated with actual status.
"Done" originally meant the platform-side plumbing worked end to end
against the simulated detector (see [ADR-0003](../docs/architecture/adr/0003-simulated-inference.md));
as of [ADR-0010](../docs/architecture/adr/0010-real-pretrained-inference.md)
that plumbing now runs real pretrained-model inference instead — still not
a custom-trained model (out of scope), but a genuine step past simulation.

## Phase 1 — Infrastructure foundation
Camera onboarding by IP, RTSP ingestion, basic inference pipeline,
database schema, basic live view.
**Status: done.**

## Phase 2 — Violation detection logic
Safety + Vehicle detection wired end to end, full event pipeline,
violation review UI.
**Status: done**, and now running **real inference** (two pretrained
YOLOv8-nano models — [ADR-0010](../docs/architecture/adr/0010-real-pretrained-inference.md))
instead of the earlier simulator. Two caveats still open: (1) vehicle
violation is a zone heuristic on top of real person detection, not a
trained "truck-bed rider" class — no such pretrained model exists; a
custom-trained model is the eventual real fix and remains a separate
future workstream. (2) it runs CPU-only on the lab host (no GPU), sized
for demo throughput, not production camera counts — see the HLD's
non-functional notes.

## Phase 3 — Notification & authentication
Email alerting, SSO with role separation, Admin Dashboard for user
management.
**Status: done.**

## Phase 4 — Reporting & full RBAC
Trend analytics, exportable reports, fine-grained roles beyond
operator/admin.
**Status: mostly done** — see [ADR-0011](../docs/architecture/adr/0011-real-app-ia-and-rbac-backport.md).
`GET /api/reports/summary` covers trend/category-split/per-camera/
completion-rate/response-time (Laporan & Analitik page); a third role
(**Supervisor**, between Operator and Admin) is real and enforced
server-side. Still open: exportable reports (no download/export action exists yet —
the page is view-only) and permissions finer than role (e.g. "Operator
can only see cameras at Site X" — see F6/F5 in [PRD.md](PRD.md)).

## Phase 5 — Hardening & scale
Platform health monitoring (Prometheus/Grafana), message broker between
inference and the API for higher camera counts, TLS, evidence object
storage (snapshots/clips).
**Status: not started.** Current architecture is documented as
sufficient for the 10–50 camera demo scale — see the non-functional
notes in [HLD.md](../docs/architecture/HLD.md).

## Pending decisions blocking a real (non-demo) rollout

- Real GPU server specification (camera-per-GPU capacity planning). The
  lab host confirmed has no GPU (`nvidia-smi` absent); current inference
  is CPU-only nano models sized for that — see [ADR-0010](../docs/architecture/adr/0010-real-pretrained-inference.md).
- A custom-trained "truck-bed rider" model, to replace the person-in-zone
  heuristic currently standing in for it (no pretrained model exists for
  that specific behavior) — this is the actual AI Engineer workstream the
  platform is built to plug into.
- Real camera resolution/FPS (affects inference load & bandwidth
  planning), and per-camera "cargo bed" zone calibration for vehicle
  cameras once real cameras replace the demo photo loops.
- Corporate SMTP relay credentials, to replace the Mailpit demo catcher.
- Official Pertamina EP brand guideline (exact PMS/hex values, vector
  logo formats) — the real logo raster is already in use, but the
  palette was read visually off it rather than a guideline doc; see
  [ADR-0009](../docs/architecture/adr/0009-brand-palette-from-logo.md).
- Video evidence retention policy — snapshots are now captured and stored
  (see [ADR-0010](../docs/architecture/adr/0010-real-pretrained-inference.md)),
  but nothing prunes old ones yet; how long to keep them is still an open
  question once Phase 5's fuller object storage lands.
- Licensing review for `apps/inference/models/` before any real
  production use — see that folder's `NOTICE.md`.
- TLS certificate approach (internal CA vs. public CA) once this leaves
  the lab network.
