# ADR-0010: Swap simulated inference for real pretrained-model inference

**Status**: Accepted

**Supersedes**: does not invalidate [ADR-0003](0003-simulated-inference.md)
— training a model is still explicitly out of scope, and the reasoning
there for why the platform was built decoupled from the model still
holds. This ADR records the next step: instead of a random event
generator, `apps/inference` now runs two small, publicly available
**pretrained** models, unmodified, so the same platform can be demoed on
real (if placeholder) input rather than synthetic ones.

## Context

The user asked, in effect: when the AI Engineer produces a trained model,
how does it actually plug into this platform, and is there an existing
pretrained model that lets this be demoed for real right now rather than
staying simulated indefinitely?

Two violation classes are in scope:

- **APD Detection** — a person not wearing a hardhat/helmet.
- **Vehicle Violation** — a person riding in the bed of a truck.

## Decision

### 1. Use existing pretrained models, don't train anything

- **APD**: [`keremberke/yolov8n-hard-hat-detection`](https://huggingface.co/keremberke/yolov8n-hard-hat-detection)
  — a YOLOv8-nano model already fine-tuned on the public "Hard Hat
  Workers" dataset, classes `Hardhat` / `NO-Hardhat`, mAP@0.5 0.836 per
  its model card. Used as-is.
- **Vehicle**: there is no public pretrained class for "person riding in
  a truck bed" — that's a specific behavior, not a generic object class,
  and nobody has published a model for it. Rather than fake it or block
  on a custom training effort (out of scope), `apps/inference` uses
  Ultralytics' own stock COCO-pretrained `yolov8n.pt` for its generic
  `person` class, and adds a **zone heuristic**: a detected person whose
  bounding-box centroid falls inside that camera's configured "cargo bed"
  zone counts as a violation. This is real, working person detection with
  a rule on top of it — not a trained "truck-bed rider" recognizer. A real
  deployment calibrates each camera's zone during commissioning (walk the
  physical bed's corners in the live view); the shipped `DEFAULT_ZONE` is
  a placeholder covering most of the frame, sized for the demo cameras.
- Both are **nano** variants (~6 MB each) specifically so CPU inference on
  the lab host is feasible without a GPU — see the HLD's non-functional
  notes for the resulting throughput expectation (roughly 1 frame per
  camera per `SAMPLE_INTERVAL_SECONDS`, not real-time video-rate).

### 2. Replace `apps/inference-sim` with `apps/inference`

Same integration contract as before — `GET /internal/cameras` on
startup, `POST /api/events` per detection — so no backend or frontend
change was *required* to plug this in (some were made anyway, see below,
because they were genuinely missing pieces, not because the contract
changed). `apps/inference-sim` is kept on disk, unwired from
`docker-compose.yml`, purely as a record of the earlier milestone (see
its `DEPRECATED.md`).

### 3. Feed it real (if placeholder) camera content

There are no live cameras on the lab host. `infra/demo-camera/`
previously published a synthetic color pattern to MediaMTX — enough to
prove RTSP → HLS worked, but useless as input to a real model (nothing to
detect). It now loops one real, CC-licensed/public-domain still photo per
camera instead (see `infra/demo-camera/images/NOTICE.md` for exact
sources and licenses), so the pretrained models have genuine content to
run against and the demo shows real detections, not scripted ones.

### 4. Two small platform gaps this surfaced, fixed as part of this change

- `Camera` had no `category` field — nothing told the inference worker
  which model to run against a given camera. Added `category` (`apd` |
  `vehicle`), migrated in-place via an idempotent `ALTER TABLE ... ADD
  COLUMN IF NOT EXISTS` so this doesn't require dropping the postgres
  volume (see LLD §1).
- `Violation.snapshot_ref` existed but was never populated (no object
  storage wired up). Added a `snapshots` named volume mounted into
  `backend`, `POST /api/events` now accepts an optional
  `snapshot_base64` and writes it there, and `GET
  /api/violations/{id}/snapshot` serves it back. The dashboard's
  violation table now shows a "Lihat snapshot" link when one exists.

## Consequences

- The platform is demoable end to end on genuine model output: a real
  photo without a hardhat produces a real "NO-Hardhat" detection, a real
  email, a real dashboard update — not a `random.random()` roll.
- The vehicle-violation "detection" is honestly a heuristic, not a
  trained capability, and is documented as such in three places (this
  ADR, the HLD's "what's simulated vs real" table, and
  `inference.py`'s own module docstring) so nobody downstream mistakes it
  for more than it is.
- Neither model's license was fully cleared for production use at the
  time of writing (the hardhat model's card states no license; the
  Ultralytics weights are AGPL-3.0) — acceptable for this internal
  PoC/demo, called out in `apps/inference/models/NOTICE.md` and folded
  into the existing "rotate/verify everything here before real
  production" rule in `docs/runbook/credentials.md`.
- CPU-only inference means this does not represent production-grade
  latency or camera-count scaling. When the AI Engineer's real trained
  model is ready, or when this needs to scale past a handful of cameras,
  the natural next step is GPU inference — `apps/inference` was written
  so that swapping `hardhat.pt`/`yolov8n.pt` for a real trained model file
  is a drop-in change (same `/api/events` contract), but the
  CPU-sizing assumption should be revisited then.
