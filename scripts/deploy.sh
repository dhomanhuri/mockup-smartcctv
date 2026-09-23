#!/usr/bin/env bash
# Sync this repo to the target host and bring the whole stack up there.
# See ADR-0016 — this replaces running the equivalent rsync/ssh/docker
# commands by hand, so the deploy procedure is reproducible and lives in
# the repo instead of only in someone's shell history.
#
# Usage:
#   DEPLOY_PASSWORD='...' scripts/deploy.sh
#
# Everything is overridable via env var so this isn't a Pertamina-EP-box-
# specific script wearing a generic name:
#   DEPLOY_HOST      (default: 192.168.56.199)
#   DEPLOY_USER      (default: busdev)
#   DEPLOY_PATH      (default: /home/busdev/smart-cctv-ai)
#   DEPLOY_PASSWORD  (required — SSH password auth; use SSH keys and drop
#                     sshpass entirely on a host that supports it)
#
# Deliberately does NOT hardcode DEPLOY_PASSWORD in this file — that's
# exactly the kind of thing ADR-0016 says must be config, not a literal.

set -euo pipefail

DEPLOY_HOST="${DEPLOY_HOST:-192.168.56.199}"
DEPLOY_USER="${DEPLOY_USER:-busdev}"
DEPLOY_PATH="${DEPLOY_PATH:-/home/busdev/smart-cctv-ai}"

if [ -z "${DEPLOY_PASSWORD:-}" ]; then
  echo "DEPLOY_PASSWORD is not set — export it (or switch this script to" >&2
  echo "SSH-key auth and drop sshpass) before running." >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH="sshpass -p ${DEPLOY_PASSWORD} ssh -o StrictHostKeyChecking=accept-new"
RSYNC="sshpass -p ${DEPLOY_PASSWORD} rsync -az --delete"

echo "==> Ensuring ${DEPLOY_PATH} exists on ${DEPLOY_HOST}"
${SSH} "${DEPLOY_USER}@${DEPLOY_HOST}" "mkdir -p '${DEPLOY_PATH}'"

echo "==> Syncing repo to ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}"
${RSYNC} \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'node_modules' \
  "${REPO_ROOT}/" "${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_PATH}/"

echo "==> Building and starting the stack"
${SSH} "${DEPLOY_USER}@${DEPLOY_HOST}" "cd '${DEPLOY_PATH}' && docker compose up -d --build"

echo "==> Done. Sanity check:"
${SSH} "${DEPLOY_USER}@${DEPLOY_HOST}" "cd '${DEPLOY_PATH}' && docker compose ps"
