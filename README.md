# Smart CCTV AI

On-premise computer-vision platform for Pertamina EP: watches existing
CCTV cameras and raises alerts for **Safety Detection** (e.g. no helmet)
and **Vehicle Violation** (e.g. riding in a truck bed). This repository
is the platform — streaming, authentication, camera management,
notifications, dashboard — deliberately decoupled from the detection
model itself. It now runs **real inference** using small pretrained
YOLOv8 models (no training done here) so the whole pipeline is
demonstrable on genuine detections, not a random generator; a
custom-trained model remains a separate workstream — see
[ADR-0010](docs/architecture/adr/0010-real-pretrained-inference.md) (and
[ADR-0003](docs/architecture/adr/0003-simulated-inference.md) for the
earlier simulated milestone this replaced).

> Internal identifiers (Keycloak realm/client, Postgres db/user, Docker
> project/container names) use the slug `smart-cctv-ai`, driven entirely
> by `.env` rather than hardcoded — see
> [ADR-0016](docs/architecture/adr/0016-env-driven-internal-slug-and-simple-credentials.md),
> which supersedes the project's earlier `visionguard` codename split
> ([ADR-0008](docs/architecture/adr/0008-product-rename-vs-internal-slug.md)).

**Start here:**
- Never touched this repo before? → [docs/architecture/HLD.md](docs/architecture/HLD.md)
- Deploying it? → [docs/runbook/deployment.md](docs/runbook/deployment.md)
- Something's broken and it feels familiar? → [docs/runbook/troubleshooting.md](docs/runbook/troubleshooting.md)
- Need a login/credential? → [docs/runbook/credentials.md](docs/runbook/credentials.md)
- Why is it built this way? → [docs/architecture/adr/](docs/architecture/adr/)
- What is this *for*, and what's left to build? → [product/BRD.md](product/BRD.md), [product/PRD.md](product/PRD.md), [product/roadmap.md](product/roadmap.md)

## Repository map

```
smart-cctv-ai/           # checkout folder — see ADR-0016 for why this name isn't load-bearing
├── docker-compose.yml   # `include:`s the two files below, pins the Compose project name
├── .env                 # every ${VAR} referenced by apps/ and infra/ compose files
├── assets/brand/        # canonical Pertamina EP logo — apps/frontend and infra/keycloak
│                        # each keep their own copy of it, see ADR-0009
│
├── apps/                # the product
│   ├── docker-compose.yml
│   ├── backend/         # FastAPI — cameras, violations, auth, admin API, snapshots
│   ├── frontend/        # 6 pages + admin.html, role-aware (Operator/Supervisor/Admin) — vanilla JS, no build step, see ADR-0011
│   └── inference/       # real pretrained-model inference worker (ADR-0010; superseded and deleted the earlier inference-sim)
│
├── infra/               # what the product runs on
│   ├── docker-compose.yml
│   ├── keycloak/        # realm import + custom split-screen login theme
│   ├── mediamtx/        # RTSP → HLS streaming config
│   ├── reverse-proxy/   # nginx — single ingress on port 80
│   └── demo-camera/     # loops real demo photos as RTSP sources — no live cameras on the lab host
│
├── docs/                # architecture + operations
│   ├── architecture/
│   │   ├── HLD.md       # system-level design, diagrams, service table
│   │   ├── LLD.md       # data model, API surface, sequence diagrams
│   │   └── adr/         # why each non-obvious decision was made
│   └── runbook/
│       ├── deployment.md
│       ├── troubleshooting.md
│       └── credentials.md
│
├── scripts/              # deploy.sh, reset-realm.sh — see ADR-0016
│
└── product/              # business & product requirements
    ├── BRD.md
    ├── PRD.md
    └── roadmap.md
```

Why the split into `apps/`/`infra/`, and why the compose files are
structured the way they are: [ADR-0007](docs/architecture/adr/0007-repo-and-compose-layout.md).

## Quick start

```bash
docker compose up -d --build
```

Or, from a dev machine, `scripts/deploy.sh` (see [docs/runbook/deployment.md](docs/runbook/deployment.md)).

Then open `http://<host>/` — full detail, URLs, and reset procedures in
[docs/runbook/deployment.md](docs/runbook/deployment.md).

## What's real vs. simulated

| Piece | Status |
|---|---|
| Camera streaming (RTSP → HLS via MediaMTX) | Real |
| Authentication (Keycloak, PKCE, 3-role RBAC — Operator/Supervisor/Admin) | Real, enforced server-side — see [ADR-0011](docs/architecture/adr/0011-real-app-ia-and-rbac-backport.md) |
| Email notifications (SMTP) | Real, pointed at a local catcher instead of a corporate relay |
| Camera CRUD, violation review, live WebSocket feed, snapshots | Real |
| Camera footage | Placeholder — real CC-licensed photos looped by `demo-camera`, not live cameras |
| APD (no-hardhat) detection | **Real inference**, pretrained model — see [ADR-0010](docs/architecture/adr/0010-real-pretrained-inference.md) |
| Vehicle violation detection | Real person detection + a **zone heuristic** (no pretrained "truck-bed rider" model exists) — see [ADR-0010](docs/architecture/adr/0010-real-pretrained-inference.md) |
| Model training | Still out of scope — both models are used exactly as published |

All demo credentials are exactly that — demo. Rotate everything in
`.env` and the Keycloak realm before any real deployment; see
[docs/runbook/credentials.md](docs/runbook/credentials.md).
