# ADR-0007: `apps/` vs `infra/`, one included Compose tree instead of one flat file

**Status**: Accepted

## Context

The project started as one flat folder (`backend/`, `frontend/`,
`keycloak/`, `mediamtx/`, ... all siblings) with a single 140-line
`docker-compose.yml`. That's fine for a handful of services, but it mixes
two different concerns with two different rates of change: the product
itself (backend/frontend/inference) and the infrastructure it runs on
(databases, identity, streaming, reverse proxy). It also made a single
compose file long enough that scanning it for "what does the app
actually consist of" took real effort.

Splitting compose files raises its own question: separate standalone
stacks (`cd infra && docker compose up`, `cd apps && docker compose up`
independently), or something that stays one command?

## Decision

Two-level split:

- **Folders**: `apps/` (backend, frontend, inference-sim — the product)
  and `infra/` (postgres, keycloak, mediamtx, demo-camera, mailpit,
  reverse-proxy — what the product runs on).
- **Compose files**: `apps/docker-compose.yml` and
  `infra/docker-compose.yml` each define only their own domain's
  services, but neither is meant to run standalone (`apps`'s services
  `depends_on` names like `postgres` that only exist in `infra`). A root
  `docker-compose.yml` combines them with Compose's `include:` directive,
  so `docker compose up -d --build` from the repo root still brings up
  the whole stack in one project/network, one command, same as before.

Considered and rejected: fully independent stacks per domain. This is a
single person/team operating the whole platform as one unit — infra and
app don't have separate deploy lifecycles here, so paying the operational
cost of juggling two stacks (two `up`/`down` cycles, cross-stack network
wiring) would buy nothing.

## Consequences

- `.env` stays at the repo root; Compose resolves it relative to the
  invocation directory, so it applies to variables referenced from either
  included file.
- Relative paths inside each included file (`build: ./backend`, `volumes:
  ./keycloak/import:...`) resolve relative to *that file's own
  directory*, not the root — moving a service between `apps/` and
  `infra/` means updating exactly one file.
- Verified with `docker compose config` before cutting over: all 10
  services, correct build contexts, correct volume declarations appear in
  the merged output.
