#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:=postgresql+psycopg://interview:interview@postgres:5432/interview}"
: "${REDIS_URL:=redis://redis:6379/0}"
export DATABASE_URL REDIS_URL

wait_tcp () {
  host="$1"
  port="$2"
  name="$3"
  i=0
  while [ "$i" -lt 60 ]; do
    if (echo >/dev/tcp/"$host"/"$port") >/dev/null 2>&1; then
      echo "[entrypoint] $name ready"
      return 0
    fi
    i=$((i+1))
    sleep 1
  done
  echo "[entrypoint] ERROR: $name not ready after 60s"
  return 1
}

# Wait dependencies (best-effort: only if hostnames match compose defaults)
wait_tcp postgres 5432 "postgres"
wait_tcp redis 6379 "redis"

# run migrations only when requested
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] running migrations..."
  alembic upgrade head
fi

echo "[entrypoint] exec: $*"
exec "$@"
