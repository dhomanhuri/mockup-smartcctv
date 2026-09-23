# ADR-0002: Single ingress via reverse proxy; Keycloak console on its own port

**Status**: Accepted

## Context

The first working version exposed each service on its own host port —
frontend on 8080, backend on 8000, Keycloak on 8081, MediaMTX HLS on
8888, etc. That meant wildcard CORS on the backend (every origin/port
combination is technically a different origin), a wide open-port surface,
and browser code that had to guess which port to talk to for what.

Separately, once Keycloak was reachable through the app's main port, its
own native admin console (master realm — create realms, inspect
sessions, etc.) was reachable at the same address as the product, which
blurs "this is the app" vs "this is infrastructure tooling" for anyone
hitting the server.

## Decision

Put one Nginx `reverse-proxy` in front of everything on port **80**,
routing by path (`/` → frontend, `/api` and `/ws` → backend, `/auth` →
Keycloak, `/hls` → MediaMTX). Same-origin browser calls, no CORS
configuration needed for the app to function.

Explicitly **block** `/auth/admin/*` at the reverse proxy (return 403) so
Keycloak's own admin console/API can only be reached via a **separate
exposed port (8081)** straight to the Keycloak container, bypassing the
proxy entirely.

## Consequences

- Only three ports are open to the LAN: 80 (app), 8554 (RTSP, a different
  protocol the proxy can't usefully front), 8025 (Mailpit, a debug tool).
  8081 is a fourth, deliberately separated one for infra-level access.
- Frontend code is simpler — relative paths (`/api/...`, `/hls/...`)
  work regardless of hostname/IP.
- MediaMTX's cookie-check redirect (used for its low-latency HLS variant)
  needed `proxy_redirect /hls/` on the reverse proxy, since the redirect
  Location header MediaMTX emits doesn't know about the `/hls` prefix the
  proxy strips — see [troubleshooting.md](../../runbook/troubleshooting.md).
- A real production deploy would add TLS termination at this same reverse
  proxy — one place to do it, not per-service.
