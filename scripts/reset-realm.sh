#!/usr/bin/env bash
# Force a clean Keycloak realm re-import — see "Resetting a realm/
# database cleanly" in docs/runbook/deployment.md and ADR-0016 (this
# script replaces that section's hand-typed command sequence).
#
# Keycloak's --import-realm only applies to an EMPTY Keycloak database;
# editing infra/keycloak/import/realm-smart-cctv-ai.json after the realm
# already exists does nothing until this runs. This is DESTRUCTIVE to
# Keycloak's own state (all realm users/sessions) — the app's own
# Postgres database (violations, cameras, ...) is untouched.
#
# Run this FROM the docker-compose project root (wherever `docker
# compose` already resolves this stack — the deployed directory on the
# target host, most likely).

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROJECT_NAME="$(docker compose config --format json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['name'])")"
VOLUME_NAME="${PROJECT_NAME}_kcpgdata"

echo "==> Project: ${PROJECT_NAME} (volume to drop: ${VOLUME_NAME})"
echo "==> Stopping keycloak + its database"
docker compose stop keycloak postgres-keycloak
docker compose rm -f keycloak postgres-keycloak

echo "==> Dropping ${VOLUME_NAME}"
docker volume rm "${VOLUME_NAME}"

echo "==> Bringing keycloak back up (re-imports infra/keycloak/import/*.json fresh)"
docker compose up -d postgres-keycloak keycloak

echo "==> Done. Tail the logs to confirm the import: docker compose logs -f keycloak"
