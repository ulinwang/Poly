#!/usr/bin/env bash
set -euo pipefail

command -v docker >/dev/null 2>&1 || {
  echo "docker is required" >&2
  exit 1
}
command -v curl >/dev/null 2>&1 || {
  echo "curl is required" >&2
  exit 1
}

export POLY_API_TOKEN="${POLY_API_TOKEN:-compose-smoke-operator-token-0123456789abcdef}"
export POLY_SECRET="${POLY_SECRET:-compose-smoke-encryption-secret-0123456789abcdef}"
export POLYMETL_CLICKHOUSE_PASSWORD="${POLYMETL_CLICKHOUSE_PASSWORD:-compose-smoke-clickhouse-password}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-poly-smoke}"

cleanup() {
  docker compose down --volumes --remove-orphans
}
trap cleanup EXIT

docker compose up --build --detach --wait

curl --fail --silent --show-error http://127.0.0.1:8080/ >/dev/null
curl --fail --silent --show-error http://127.0.0.1:8080/api/v1/health/live >/dev/null
curl --fail --silent --show-error http://127.0.0.1:8080/api/v1/health/ready >/dev/null

docker compose exec --no-TTY backend sh -c 'test "$(id -u)" -ne 0'

if docker compose port clickhouse 9000 >/dev/null 2>&1; then
  echo "ClickHouse must not publish port 9000 by default" >&2
  exit 1
fi

echo "Compose smoke test passed"
