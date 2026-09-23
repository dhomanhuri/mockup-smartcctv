# Deployment

## Prerequisites

- Docker + Docker Compose (v2.20+, for `include:` support) on the target
  host.
- `.env` at the repo root filled in — see
  [credentials.md](credentials.md) for what's in there and why every
  value is a demo value that needs rotating for real use.

## Bring the whole stack up

From the target host itself:

```bash
docker compose up -d --build
```

Or from a dev machine, to sync this repo to the target host and run the
above there in one step — see [ADR-0016](../architecture/adr/0016-env-driven-internal-slug-and-simple-credentials.md)
for why this is a checked-in script and not a one-off command someone
typed once:

```bash
DEPLOY_PASSWORD='...' scripts/deploy.sh
```

`DEPLOY_HOST`/`DEPLOY_USER`/`DEPLOY_PATH` env vars override the defaults
(currently `192.168.56.199` / `busdev` / `/home/busdev/smart-cctv-ai`) —
see the script's header comment.

This one command builds `apps/backend`, `apps/frontend`,
`apps/inference` (see [ADR-0010](../architecture/adr/0010-real-pretrained-inference.md)
— pulls in `ultralytics`/`opencv-python-headless`/`torch`, so this build
takes noticeably longer and produces a bigger image than the others; that
is expected), `infra/demo-camera` (×5, one per demo camera), pulls the
pinned images for everything else, and starts all 14 containers in one
project/network — see [ADR-0007](../architecture/adr/0007-repo-and-compose-layout.md)
for why the compose files are split the way they are but still come up
with one command.

`apps/inference`'s two pretrained model files are committed under
`apps/inference/models/` (a few MB each — see
`apps/inference/models/NOTICE.md` for provenance/license) rather than
downloaded at build time, so a build works even on a host with no
internet egress once the repo is copied over.

Sanity check before assuming it worked:

```bash
docker compose config --quiet && echo OK   # validates the merged config
docker compose ps                          # everything should be "Up"
```

## URLs once it's running

| What | URL |
|---|---|
| Dashboard | `http://<host>/` |
| Admin Dashboard (needs `admin` role) | `http://<host>/admin.html` |
| Keycloak console (master realm) | `http://<host>:8081/auth/admin/` |
| Email demo (Mailpit) | `http://<host>:8025` |

Credentials for all of the above: [credentials.md](credentials.md).

## Upgrading an existing deploy to the 3-role IA (ADR-0011)

The new `supervisor` role, the `ahmad.fauzi` demo user, and the light
login theme are all realm/theme changes — none of them apply to a
Keycloak that already imported the old realm (see "Resetting a
realm/database cleanly" right below; this upgrade needs that reset).
`postgres`/`pgdata` does not — the new `status`/`assigned_to`/notes/
notification-rules schema migrates in place on its own.

## Resetting a realm/database cleanly

Realm import (`infra/keycloak/import/realm-smart-cctv-ai.json`) only
applies on an **empty** Keycloak database — if you edit that file after
the realm already exists, Keycloak logs `Realm 'smart-cctv-ai' already
exists. Import skipped` and your change is silently ignored. To force a
clean re-import, run (on the host where the stack is running):

```bash
scripts/reset-realm.sh
```

See the script itself for exactly what it does — it derives the
project's actual volume name rather than assuming one, so it works
whatever the Compose project is named.

`postgres`/`pgdata` does **not** need this treatment for a model change —
`_run_schema_migrations()` in `apps/backend/app/main.py` runs idempotent
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements on every startup
for columns added after a table already existed (there's still no full
migration tool like Alembic wired in, so a genuinely destructive change —
renaming or dropping a column — would need one written by hand there).
New tables (e.g. `violation_notes`, `notification_rules` from ADR-0011)
need no entry at all — `Base.metadata.create_all` creates any table that
doesn't exist yet on its own.

For a **small** realm tweak where you don't want to lose existing users
or sessions, prefer the Keycloak Admin CLI (`kcadm.sh`, bundled in the
container) over a full reset — see
[troubleshooting.md](troubleshooting.md) for a worked example (the
`smtpServer` fix).

## Verifying real inference is actually detecting something

`apps/inference` takes ~15-30s after startup to load both models and pull
its first RTSP frame from each camera. Confirm it's really detecting
(not just running) before calling the demo good:

```bash
docker compose logs -f inference
```

Expect one `worker started` line per camera, then — once a violation
clears its confidence threshold — a `NO-Hardhat detected` or `person in
cargo zone` line followed by `emitting event`. With the shipped demo
photos (see `infra/demo-camera/images/NOTICE.md`), `demo-workshop` and
`demo-jalur` should fire within a `COOLDOWN_SECONDS` window (60s default)
of startup; `demo-gerbang`, `demo-produksi`, and `demo-parkiran` should
stay quiet (compliant/empty baselines) — if all five fire or none do,
something's wrong (check `docker compose logs mediamtx demo-camera-workshop`
for a stream that never came up).

To see the result land end to end: open the dashboard, watch a violation
appear in the Live Alert Feed within a few seconds of the log line above,
click "Lihat snapshot" on it to confirm the captured frame matches the
demo photo, and check Mailpit (`http://<host>:8025`) for the notification
email.

## Known gaps, not blockers

See the "Non-functional notes" section of
[HLD.md](../architecture/HLD.md) and the full list in
[troubleshooting.md](troubleshooting.md).
