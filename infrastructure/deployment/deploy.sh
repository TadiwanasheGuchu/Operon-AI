#!/usr/bin/env bash
# One-command deploy to a Docker host:  ./deploy.sh staging|production [VERSION]
#
# Needs: DOCKER_HOST (e.g. ssh://deploy@staging.example.com) or a local Docker daemon, the
# environment file at $OPERON_ENV_DIR/<env>.env on the machine running this, and access to the
# GHCR images. Steps: pull → migrate (one-off) → roll out → wait for health → on failure, roll
# back to the previous version (migrations are additive by policy, so the old code still runs).
set -euo pipefail

ENVIRONMENT="${1:?usage: deploy.sh staging|production [VERSION]}"
VERSION="${2:-${OPERON_VERSION:-$(git rev-parse --short=12 HEAD)}}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_DIR="${OPERON_ENV_DIR:-$HERE/envs}"
export OPERON_ENV_FILE="$ENV_DIR/$ENVIRONMENT.env"
export OPERON_IMAGE_OWNER="${OPERON_IMAGE_OWNER:?set OPERON_IMAGE_OWNER (GHCR owner)}"
export OPERON_ENVIRONMENT="$ENVIRONMENT"
[[ -f "$OPERON_ENV_FILE" ]] || { echo "Missing $OPERON_ENV_FILE" >&2; exit 2; }
set -a; source "$OPERON_ENV_FILE"; set +a

compose() { OPERON_VERSION="$1" docker compose -p "operon-$ENVIRONMENT" -f "$HERE/compose.production.yml" "${@:2}"; }
# The previous version is read from the host itself (the running API image tag), so rollback
# works from any machine, including an ephemeral CI runner.
PREVIOUS="$(docker ps --filter "label=com.docker.compose.project=operon-$ENVIRONMENT" \
  --filter "label=com.docker.compose.service=api" --format '{{.Image}}' | head -1 | sed -n 's/.*://p')"

echo "Deploying $VERSION to $ENVIRONMENT (previous: ${PREVIOUS:-none})"
compose "$VERSION" pull api worker web
compose "$VERSION" --profile migrate run --rm migrate
compose "$VERSION" up -d --remove-orphans api worker web caddy

healthy() {
  for _ in $(seq 1 30); do
    if [[ "$(compose "$1" ps api --format '{{.Health}}' | sort -u)" == "healthy" ]]; then return 0; fi
    sleep 5
  done
  return 1
}

if healthy "$VERSION"; then
  echo "Deployed $VERSION to $ENVIRONMENT."
else
  echo "Health checks failed for $VERSION." >&2
  if [[ -n "$PREVIOUS" ]]; then
    echo "Rolling back to $PREVIOUS." >&2
    compose "$PREVIOUS" up -d --remove-orphans api worker web caddy
    healthy "$PREVIOUS" && echo "Rolled back to $PREVIOUS." >&2
  fi
  exit 1
fi
