#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE_FILE=${RELEASEFOUNDRY_COMPOSE_FILE:-"$SCRIPT_DIR/../docker/docker-compose.self-host.yml"}
ENV_FILE=${RELEASEFOUNDRY_ENV_FILE:-"$SCRIPT_DIR/../docker/.env.self-host"}
MODE=${1:---up}

usage() {
  printf '%s\n' "Usage: install.sh [--check|--up]"
  printf '%s\n' "Set RELEASEFOUNDRY_ENV_FILE to a private environment file before running."
}

case "$MODE" in
  --check|--up) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

command -v docker >/dev/null 2>&1 || {
  printf '%s\n' "Docker is required." >&2
  exit 3
}
docker compose version >/dev/null 2>&1 || {
  printf '%s\n' "Docker Compose v2 is required." >&2
  exit 3
}
[ -f "$COMPOSE_FILE" ] || {
  printf '%s\n' "Compose file not found: $COMPOSE_FILE" >&2
  exit 4
}
[ -f "$ENV_FILE" ] || {
  printf '%s\n' "Private environment file not found: $ENV_FILE" >&2
  printf '%s\n' "Start from infra/docker/self-host.env.example and do not commit it." >&2
  exit 4
}

for name in RELEASEFOUNDRY_POSTGRES_AUTH_SECRET RELEASEFOUNDRY_OBJECT_STORE_ACCESS_KEY RELEASEFOUNDRY_OBJECT_STORE_SECRET_KEY; do
  grep -Eq "^${name}=.+" "$ENV_FILE" || {
    printf '%s\n' "Required variable is missing or empty: $name" >&2
    exit 5
  }
done

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" --profile commercial config --quiet
[ "$MODE" = "--check" ] && exit 0

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" --profile commercial up -d --build
printf '%s\n' "ReleaseFoundry self-host services were submitted. Verify health before accepting traffic."
