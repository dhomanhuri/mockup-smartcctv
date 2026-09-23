# Troubleshooting — issues hit during the build, and why

Real problems found while standing this platform up, kept here so nobody
re-discovers them the hard way. Each one cost real debugging time because
the symptom looked unrelated to the actual cause.

## Login silently does nothing (no redirect, no error) over plain HTTP

**Symptom**: dashboard loads its static shell, but every stat/table stays
at its placeholder value forever. Nothing in the browser ever reaches
Keycloak's login page. No visible error.

**Cause**: `window.crypto.subtle` only exists in a *secure context*
(HTTPS, or `http://localhost`) — not on a plain-HTTP LAN IP like
`http://192.168.56.199`. The PKCE `code_challenge` step called
`crypto.subtle.digest(...)`, which threw inside an `async` function that
was called without `await`, so the failure became a silent unhandled
promise rejection instead of a visible error.

**Fix**: `apps/frontend/auth.js` has a pure-JS SHA-256 implementation
(verified against Node's built-in `crypto` module output) that's used
whenever `crypto.subtle` isn't available, so PKCE still works over plain
HTTP. The one un-awaited call site was also fixed so a future failure of
this kind surfaces as a real error instead of quietly nothing happening.

## HLS playback 404s after a redirect

**Symptom**: `GET /hls/<path>/index.m3u8` returns a 302 (MediaMTX's
"cookie check" redirect for its low-latency HLS variant), and following
that redirect 404s.

**Cause**: MediaMTX's redirect `Location` header is relative to its own
root (`/<path>/index.m3u8?cookieCheck=1`) — it has no idea the reverse
proxy stripped a `/hls` prefix to reach it, so the browser follows the
redirect straight past the proxy's routing.

**Fix**: `proxy_redirect /hls/;` on the `/hls/` location block in
`infra/reverse-proxy/nginx.conf`, so Nginx rewrites the `Location` header
to restore the prefix.

## MediaMTX API returns 401 from the backend

**Symptom**: `register_pull_path` gets `{"error":"authentication
error"}` even though nothing about the request looks wrong.

**Cause**: MediaMTX's default config only grants unauthenticated `api`
access from `127.0.0.1`/`::1`. The backend calls it over the docker
network (`http://mediamtx:9997`), which is a different peer address, not
literally localhost.

**Fix**: explicit `authInternalUsers` entry in
`infra/mediamtx/mediamtx.yml` granting the `api` action to the `any` user
with no IP restriction — safe because port 9997 is never published to
the host, only reachable from other containers.

## Keycloak login theme CSS has no effect

**Symptom**: custom `login.css` loads (confirmed 200, correct path) but
the page still renders with default colors/logo — as if the stylesheet
weren't there at all.

**Cause**: the selectors were guessed from a generic PatternFly reference
instead of the real rendered DOM. `.kc-logo-text` doesn't exist in this
theme's actual markup (it's a `keycloak.v2`-only class); the dark
background is set on `<html class="login-pf">`, not `<body>`; the submit
button's real classes are `pf-c-button pf-m-primary`, not `.btn-primary`.

**Fix**: extract the actual theme files from the Keycloak image
(`docker create` + `docker cp` the `org.keycloak.keycloak-themes-*.jar`,
unzip it) and read the real `template.ftl`/`theme.properties` before
writing a single selector. See
[ADR-0004](../architecture/adr/0004-custom-keycloak-login-theme.md).

## Master admin token can't call the Admin REST API (403)

**Symptom**: a password-grant token for `kcadmin` (master realm) gets
403 on `GET /admin/realms/smart-cctv-ai`, even right after Keycloak
creates that bootstrap admin.

**Cause**: `KEYCLOAK_ADMIN`/`KEYCLOAK_ADMIN_PASSWORD` are deprecated env
vars; the bootstrap admin they create doesn't reliably carry full admin
rights via a plain password-grant token in this Keycloak version.

**Fix**: use `KC_BOOTSTRAP_ADMIN_USERNAME`/`KC_BOOTSTRAP_ADMIN_PASSWORD`
instead (same values, different env var name — see
`infra/docker-compose.yml`). Also: prefer `kcadm.sh` (bundled in the
Keycloak container, `docker exec ... /opt/keycloak/bin/kcadm.sh`) over
hand-rolled REST calls for admin CLI tasks — it handles token/grant
nuances correctly where a manual password-grant curl call didn't.

## Realm `smtpServer` doesn't apply from the import JSON

**Symptom**: `smtpServer` is set correctly in
`infra/keycloak/import/realm-smart-cctv-ai.json`, the realm imports without
error, but `kcadm.sh get realms/smart-cctv-ai` shows `"smtpServer": {}`.

**Cause**: unclear — Keycloak 26.7.3's realm-import silently drops this
field with no warning in the logs. Not resolved further; worked around
instead.

**Fix**: set it after import via `kcadm.sh`:

```bash
docker exec smart-cctv-ai-keycloak-1 /opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080/auth --realm master --user kcadmin --password "<KEYCLOAK_ADMIN_PASSWORD>"
docker exec smart-cctv-ai-keycloak-1 /opt/keycloak/bin/kcadm.sh update realms/smart-cctv-ai \
  -s smtpServer.host=mailpit -s smtpServer.port=1025 \
  -s smtpServer.from=smart-cctv-ai@pertamina-ep.local \
  -s smtpServer.fromDisplayName="Smart CCTV AI" \
  -s smtpServer.ssl=false -s smtpServer.starttls=false -s smtpServer.auth=false
```

Note: `kcadm.sh get realms/smart-cctv-ai --fields smtpServer` is itself
unreliable for nested/map fields — it can print `{}` even when the value
is genuinely set. Fetch the full realm representation and inspect the
field from that instead of trusting `--fields` for anything nested.

## Service-account client can't call the Admin API despite correct role assignment

**Symptom**: `smart-cctv-ai-user-manager`'s `client_credentials` grant
issues a token fine, but every Admin REST API call with it returns 403 —
even though the realm import JSON assigns it exactly the right
`realm-management` client roles.

**Cause**: `fullScopeAllowed: false` on the client. Keycloak only
includes a client's assigned roles in tokens it issues if the client's
scope allows it — with full scope disabled and no explicit client-scope
mapping added, the roles are assigned in the data model but never make it
into the token's claims.

**Fix**: `fullScopeAllowed: true` on `smart-cctv-ai-user-manager` in
`infra/keycloak/import/realm-smart-cctv-ai.json`. See
[ADR-0006](../architecture/adr/0006-service-account-for-admin-api.md).

## A fixed frontend bug still shows for some viewers after redeploying

**Symptom**: a real fix goes out (rebuild + redeploy `frontend`),
`curl`ing the file straight from the server shows the new content, but a
browser that already had the page open — or even one just reloading
normally (not a hard refresh) — keeps showing the old, buggy behavior.
Hit this exact way with the avatar-shows-"?"/wrong-role-pill bug (ADR-0011):
the underlying cause had already been fixed in `auth.js`, but a viewer's
browser kept serving its own cached copy of the old `auth.js` instead of
fetching the new one.

**Cause**: `nginx:1.27-alpine`'s stock config serves static files with no
explicit `Cache-Control`, which leaves each browser free to cache
`.js`/`.css`/`.html` heuristically and skip revalidation for a while —
there was nothing telling it the file could have changed.

**Fix**: `apps/frontend/nginx.conf` (a custom config now baked into the
`frontend` image, replacing nginx's default) sets `Cache-Control:
no-cache, must-revalidate` on `.html`/`.js`/`.css` responses, forcing a
revalidation check on every load instead of trusting a heuristic TTL. A
genuinely stuck viewer still needs one hard refresh (Ctrl+Shift+R) to
discard whatever it already cached before this config existed; every
load after that self-corrects.

## `/api/*` returns 502 after rebuilding just `backend`

**Symptom**: `docker compose up -d --build backend` (or any command that
recreates `backend` alone) finishes cleanly, `backend`'s own logs look
fine, but every request through the reverse proxy — `/api/cameras`,
`/api/violations`, even `/api/health` — gets a 502 from nginx.
`reverse-proxy`'s logs show `connect() failed (111: Connection refused)
while connecting to upstream ... upstream: "http://172.20.0.X:8000/..."`
where `.X` is *not* the new container's actual IP.

**Cause**: plain `proxy_pass http://backend:8000;` in nginx resolves the
hostname `backend` **once**, when the worker process starts, and caches
that IP for the worker's lifetime. Recreating the `backend` container
(rebuild, `up -d`, anything Compose treats as a new container rather than
the same one restarting) gives it a new IP on the docker network —
nginx keeps proxying to the old, now-dead one until it's restarted too.
Found this rebuilding `apps/inference` right after `backend` gained the
`category` field ([ADR-0010](../architecture/adr/0010-real-pretrained-inference.md)):
the dashboard silently 502'd until `docker compose restart reverse-proxy`
was run by hand.

**Fix**: made this a non-issue instead of a step to remember —
`infra/reverse-proxy/nginx.conf` now sets `resolver 127.0.0.11 valid=10s
ipv6=off;` (Docker's embedded DNS) and puts every upstream host in an
nginx variable (`set $backend_upstream backend:8000; proxy_pass
http://$backend_upstream;`) instead of a bare literal — a variable in
`proxy_pass` forces nginx to re-resolve through that resolver on every
request (respecting the 10s TTL) rather than caching forever. Verified by
`docker compose up -d --force-recreate backend` and confirming
`/api/cameras` still returns 200 with zero manual intervention. If you
ever see this symptom again, check whether a location's `proxy_pass` got
added back as a bare `http://servicename:port` instead of following this
pattern.

## State that doesn't survive a restart

Two gaps found by asking "is everything actually persistent?" rather
than from a failure:

- **MediaMTX** keeps dynamically-registered RTSP paths in memory only.
  Fixed by having `backend` re-assert every camera's path on startup and
  every 5 minutes (`_reregister_camera_streams` in
  `apps/backend/app/main.py`) — see
  [ADR-0005](../architecture/adr/0005-mediamtx-for-streaming.md).
- **Mailpit** had no volume, so its inbox reset on every restart. Fixed
  with a `mailpitdata` named volume + `MP_DATABASE` pointed at a file
  inside it.

## Every camera stuck on "no frame available yet" forever

**Symptom**: `docker logs inference` shows every camera logging `no frame
available yet` in an endless loop — not intermittent, never recovers on
its own, even minutes later. New alerts stop appearing anywhere in the
app.

**Cause, two layers**:

1. **Host CPU oversubscription.** Five `demo-camera` containers each run
   an `ffmpeg -re ... libx264` transcode continuously; on a 4-core lab
   VM, five of those at 1280x720/`-preset veryfast` plus
   `apps/inference`'s own CPU-bound YOLO inference add up to more
   demand than the host has cores. `uptime`'s load average climbing well
   past the core count (seen: ~28 on 4 cores) is the tell. Once ffmpeg
   falls behind real time under that contention it never catches back
   up — output was found to be running at roughly 1/20th real-time speed
   after sustained load. Fixed by dropping to 960x540 +
   `-preset ultrafast` in `infra/demo-camera/entrypoint.sh` — check
   `docker stats` per `demo-camera-*` container settles comfortably
   under 100% each afterward, not 100-240%.
2. **`apps/inference` never reconnects on a silent read failure.**
   `cv2.VideoCapture.read()` returns `(False, None)` when the
   upstream RTSP source is gone — it doesn't raise, so the
   `except Exception: reconnect` branch in `camera_worker` never
   triggered. Restarting the `demo-camera-*` containers (layer 1's fix)
   was not enough by itself — `inference` needed its own restart to open
   a fresh `cv2.VideoCapture` against the new RTSP session before it
   detected anything again. Fixed properly in
   `apps/inference/inference.py`: `run_apd_camera`/`run_vehicle_camera`
   now return whether they actually read a frame, and `camera_worker`
   forces a reconnect after `MAX_CONSECUTIVE_FAILURES` (5, ~20s) of
   silent failures — not just on a hard exception.

**Fix, if hit again**: check `uptime` first. If load average is far
above the core count, it's layer 1 (CPU contention) — `docker stats`
confirms which containers are the ones eating it. Restarting
`demo-camera-*` clears an already-stuck ffmpeg's backlog; `inference`
should now self-heal within ~20s on its own (layer 2's fix) without
needing a manual restart too.
