# ADR-0016: Env-driven internal slug, dropped compliance/target tracking, simplified demo credentials, scripted realm resets

**Status**: Accepted

## Context

Three separate asks landed in the same session:

1. Looking at the app in practice, the "Kepatuhan & Target HSSE"
   (compliance vs. `weekly_target`) feature added in ADR-0014 read badly
   in the demo: the target was a made-up placeholder number with no real
   operational baseline behind it, so every category permanently showed
   "MELEBIHI TARGET" in red — noise, not signal. Decision: *"keknya yang
   target2 itu gak perlu deh dimasukin"* — drop it everywhere (Dashboard,
   Laporan & Analitik, Pengaturan, PDF export, Recurring Report email).
2. The user noticed `visionguard` still throughout the workspace (folder
   tree, container names) and asked for it to be gone in favor of "Smart
   CCTV AI", container names included, accepting that this may require
   resetting Keycloak/Postgres from scratch. Separately, and pointedly:
   *"semua env yang dinamis di app/infra harus jadikan env, gak boleh di
   hardcoded"* — the actual root cause of why a rename touched ~30 files
   in the first place was that the realm name/client id were hardcoded
   as literal strings in many places instead of flowing from config.
3. Whatever infra changes come out of this (realm creation included)
   must be a **documented, scripted** procedure, not an interactive
   session running one-off `ssh`/`docker` commands that leave no trace
   in the repo.

This explicitly revisits [ADR-0008](0008-product-rename-vs-internal-slug.md),
which had deliberately kept `visionguard` as the internal slug specifically
to avoid this reset. That reasoning was sound at the time; the user has
now made the opposite tradeoff explicitly and accepted the reset cost.

## Decision

### Dropped: weekly_target / compliance

Removed entirely rather than kept-but-hidden: `NotificationRule.weekly_target`
(column left physically in place on an already-migrated DB per this
project's additive-only migration policy, just unmapped — see
`models.py`), `ComplianceOut`, the `compliance` field on `ReportSummaryOut`,
the compliance table in the PDF report, the "KEPATUHAN & TARGET HSSE"
section in the Recurring Report email, and the corresponding UI blocks
in `index.html` / `reports.html` / `settings.html`. If a real HSSE target
is defined later with an actual baseline behind it, re-add it then —
this was premature.

### Internal slug: `visionguard` → `smart-cctv-ai`, now env-driven

New product-wide slug: `smart-cctv-ai` (kebab-case for Keycloak
realm/client/Docker identifiers, `smart_cctv_ai` for Postgres, which
doesn't allow bare hyphens in unquoted identifiers). Applied to: the
Keycloak realm and both client ids, the Postgres app database/user, and
every internal identifier that follows from those.

More importantly, **every one of those values now flows from `.env`**
instead of being a literal string baked into code:

- `.env` gains `KEYCLOAK_REALM` and `KC_CLIENT_ID` (previously the
  backend hardcoded `KEYCLOAK_REALM: visionguard` directly in
  `apps/docker-compose.yml`, and every frontend page hardcoded
  `realm: "visionguard", clientId: "visionguard-dashboard"` inline).
- `apps/docker-compose.yml`'s backend service reads `${KEYCLOAK_REALM}`
  instead of a literal.
- The **frontend** — static HTML/JS, no build step (ADR-0011) — has no
  native way to read a container's env vars at request time. Fixed with
  the nginx base image's own `docker-entrypoint.d/20-envsubst-on-templates.sh`
  hook: `apps/frontend/config.js.template` gets `envsubst`'d into
  `/usr/share/nginx/html/config.js` at container start (output dir
  redirected there via `ENV NGINX_ENVSUBST_OUTPUT_DIR` in the Dockerfile),
  populated from the `KEYCLOAK_REALM`/`KC_CLIENT_ID` env vars now passed
  to the `frontend` service. Every page loads `config.js` before
  `auth.js` and reads `window.APP_CONFIG.realm` / `.clientId` — zero
  pages hardcode the realm/client name any more.
- `infra/keycloak/import/realm-visionguard.json` is renamed to
  `realm-smart-cctv-ai.json` and its `realm`/`clientId`/`secret`/user
  fields updated to match. This file is the one piece that's still a
  static literal — Keycloak's `--import-realm` reads a plain JSON file
  with no templating support, so "env-driven" here means "kept in
  lockstep with `.env` by convention and a comment on both sides",
  documented rather than automated. `scripts/reset-realm.sh` (below) is
  what actually applies it.
- Python fallback defaults (`os.getenv("KEYCLOAK_REALM", "visionguard")`
  in `auth.py`/`keycloak_admin.py`, the `DATABASE_URL` fallback in
  `database.py`) updated to match — these were already env-driven in
  practice (compose always supplies the real value), just had a stale
  hardcoded string as their *fallback*.
- Docker container/volume/network name prefix: rather than rename the
  actual checkout folder (Compose derives the project name from the
  folder's basename by default — high blast-radius to change mid-flight,
  zero user-facing benefit), the root `docker-compose.yml` now pins
  `name: smart-cctv-ai` explicitly. Same effect (`smart-cctv-ai-backend-1`
  etc.) without touching the filesystem path.
- Logger namespaces (`visionguard.backend`, `.notifications`, `.streaming`,
  `.inference`) renamed to `smart_cctv_ai.*` for full consistency — purely
  cosmetic (never user-visible), done anyway since it was trivial.

### Simplified demo credentials

Every password in `.env` and the realm import (Postgres, Keycloak DB,
Keycloak master admin, and all three app login users) is now the single
value `busDev123!` — matching the SSH credential already in use for this
box, one thing to remember for the whole demo. Usernames simplified too:
`admin.visionguard` → `admin`, `ahmad.fauzi` → `supervisor` (display name
also genericized to "Supervisor HSE"), `operator` unchanged. The one
exception is `KC_USER_MANAGER_SECRET` (the backend's service-account
client secret) — left as a random-looking string, since that's a
machine credential nobody types, not a login password; conflating the
two would be a bad habit even in a demo. This is a deliberate,
demo-only simplification — see the "Rotate every value here before any
real production rollout" header already on `.env`, unchanged by this
ADR.

### Scripted, documented infra changes

Added `scripts/deploy.sh` (rsync the repo to the target host + `docker
compose up -d --build` there) and `scripts/reset-realm.sh` (the "stop
keycloak+postgres-keycloak, drop the keycloak volume, bring keycloak
back up" sequence from `deployment.md`'s "Resetting a realm/database
cleanly" section, now a checked-in script instead of hand-typed
commands). Both take the target host/user as env vars with defaults
matching this deploy, so the same script works for whoever runs it next
without editing it. `deployment.md` points at both instead of listing
raw command sequences as the primary instructions.

## Consequences

- This forces exactly the reset ADR-0008 was written to avoid: existing
  Keycloak sessions and the Postgres `smart_cctv_ai`/`keycloak` databases
  need to be recreated from empty (old volumes named under the
  `visionguard` project are orphaned, not migrated) — accepted
  explicitly by the user, and the app's own seed logic
  (`_seed_demo_cameras`, `_seed_notification_rules`, `_seed_report_schedule`)
  already repopulates a fresh database with working demo data, so this
  is a clean reset, not a broken one.
- A future re-rename is now genuinely "edit `.env` + rename one JSON file
  + run `scripts/reset-realm.sh`" — no more grepping the codebase for a
  literal string across ~30 files, which is what made this exercise
  large in the first place.
- `apps/inference-sim/` (already fully unwired since ADR-0010, its own
  `DEPRECATED.md` said "safe to delete once nobody needs the history")
  and a stray local `__pycache__/` directory were deleted as part of the
  same workspace cleanup pass — unrelated to the rename, just found
  while auditing the tree file-by-file per the same request.
