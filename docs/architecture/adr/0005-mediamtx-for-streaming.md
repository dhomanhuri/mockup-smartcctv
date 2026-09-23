# ADR-0005: MediaMTX for RTSP → browser streaming

**Status**: Accepted

## Context

Browsers can't play RTSP directly. Something needs to sit between IP
cameras (RTSP) and the dashboard (which can play HLS or WebRTC). The
platform also needs "add a camera by IP" to actually produce a watchable
stream, not just a database row — which means paths need to be
registerable **at runtime**, not only via a static config file edited
before startup.

## Decision

Use **MediaMTX** (`bluenviron/mediamtx`) as that bridge:

- It exposes a REST control API (port 9997, internal-only) that the
  backend calls to add (`POST /v3/config/paths/add/{id}`) or remove
  (`POST /v3/config/paths/delete/{id}`) a pull path whenever a camera's
  `rtsp_url` is set, changed, or cleared.
- Paths are registered with `sourceOnDemand: true` — MediaMTX only pulls
  from the camera once someone actually opens the stream.
- One demo camera (`infra/demo-camera`, a synthetic ffmpeg source) is
  wired as a **push** source into MediaMTX at a fixed path, proving the
  RTSP → HLS → browser path really works without needing a real camera on
  the lab network.

## Consequences

- Adding a camera with a real RTSP URL in the UI makes it watchable
  immediately — no MediaMTX restart or config edit needed.
- MediaMTX's default config only allows unauthenticated API access from
  `127.0.0.1` — since the backend calls it over the docker network (not
  literally localhost), this needed an explicit `authInternalUsers` entry
  granting the `api` action. Safe here because port 9997 is never
  published to the host. See
  [troubleshooting.md](../../runbook/troubleshooting.md).
- Registered paths live in MediaMTX's memory only, not on disk — a
  MediaMTX-only restart loses them. `backend` re-asserts every camera's
  path on its own startup and every 5 minutes to self-heal this (see
  `_reregister_camera_streams` in `apps/backend/app/main.py`).
