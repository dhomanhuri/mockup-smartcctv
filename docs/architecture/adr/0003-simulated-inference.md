# ADR-0003: Simulate inference instead of training/integrating a real model

**Status**: Accepted (deliberate scope boundary, not a shortcut taken by accident)

## Context

The platform plan calls for two AI detection classes — Safety Detection
(e.g. no helmet) and Vehicle Violation (e.g. riding in a truck bed).
Training and integrating those models is a separate, substantial
workstream (data collection, labeling, training, GPU inference
optimization) that this platform build was explicitly scoped to not
include — the goal here is the platform the model plugs into, not the
model.

## Decision

`apps/inference-sim` plays the role a real edge inference worker would,
end to end except for the actual computer vision:

- Fetches the camera list from `GET /internal/cameras` on startup.
- Runs one loop per camera that narrates the real pipeline's stages
  (frame capture → inference → tracking → rule check) via log lines.
- On a randomized, per-camera-biased cadence, produces a candidate
  violation with a confidence score; only candidates clearing a
  per-class threshold get submitted.
- Submits via `POST /api/events` — **the same contract a real model
  worker would use.**

## Consequences

- Every downstream piece (event storage, email notification, WebSocket
  push, dashboard) is exercised with realistic-looking, continuously
  arriving data, without needing a GPU or trained weights.
- Swapping in a real model means replacing the contents of
  `apps/inference-sim` (or adding a new service) with something that
  reads real RTSP, runs a real model, and calls the same `/api/events`
  endpoint — no backend/frontend changes required.
- Anyone reading dashboard data must remember it's synthetic. The
  frontend footer says so; this ADR is the durable record of why.
