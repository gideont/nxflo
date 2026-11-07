#!/bin/bash
set -euo pipefail

CONTAINER=nxflo-static
IMAGE=nxflo-static:latest
PORT=9001
API_CONTAINER=nxflo-portal-api
API_IMAGE=nxflo-portal-api:latest
WORKER_CONTAINER=nxflo-generator-worker
API_ENV_ARGS=()
ENV_FILE="$(cd "$(dirname "$0")" && pwd)/.env"
if [ -f "$ENV_FILE" ]; then API_ENV_ARGS=(--env-file "$ENV_FILE"); fi
NETWORK=nxflo-portal-network
VOLUME=nxflo-bms-data
CLIENT_ID=${BMS_GOOGLE_CLIENT_ID:-658474600728-2rikqi8fb8r0qk5l4ir10a1goe42ohof.apps.googleusercontent.com}
OWNER_EMAIL=${BMS_OWNER_EMAIL:-gideont@gmail.com}
PUBLIC_ORIGIN=${BMS_PUBLIC_ORIGIN:-https://www.nxflo.com}

# Validate images before touching either running service.
docker image inspect "$IMAGE" "$API_IMAGE" >/dev/null
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null
docker volume inspect "$VOLUME" >/dev/null 2>&1 || docker volume create "$VOLUME" >/dev/null

previous_worker=$(docker inspect "$WORKER_CONTAINER" --format '{{.Image}}' 2>/dev/null || true)
docker stop "$WORKER_CONTAINER" >/dev/null 2>&1 || true
docker rm "$WORKER_CONTAINER" >/dev/null 2>&1 || true

backup_stamp=$(date -u +%Y%m%dT%H%M%S%N)
docker run --rm --network none -v "$VOLUME:/data" "$API_IMAGE" \
  python -m portal_api.backup "/data/backups/predeploy-${backup_stamp}.sqlite3"

previous_api=$(docker inspect "$API_CONTAINER" --format '{{.Image}}' 2>/dev/null || true)
previous_site=$(docker inspect "$CONTAINER" --format '{{.Image}}' 2>/dev/null || true)
start_api() {
  docker run -d --name "$API_CONTAINER" --network "$NETWORK" --restart unless-stopped \
    -v "$VOLUME:/data" "${API_ENV_ARGS[@]}" \
    -e BMS_DATABASE_PATH=/data/bms_hub.sqlite3 \
    -e "BMS_GOOGLE_CLIENT_ID=$CLIENT_ID" -e "BMS_OWNER_EMAIL=$OWNER_EMAIL" \
    -e "BMS_PUBLIC_ORIGIN=$PUBLIC_ORIGIN" "$1"
}
start_worker() {
  docker run -d --name "$WORKER_CONTAINER" --network "$NETWORK" --restart unless-stopped \
    -v "$VOLUME:/data" "${API_ENV_ARGS[@]}" \
    -e BMS_DATABASE_PATH=/data/bms_hub.sqlite3 "$1" python -m portal_api.generator_worker
}
wait_api() {
  for attempt in $(seq 1 20); do
    if docker exec "$API_CONTAINER" python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/bms_integration_hub/api/health',timeout=2)" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

docker stop "$API_CONTAINER" >/dev/null 2>&1 || true
docker rm "$API_CONTAINER" >/dev/null 2>&1 || true
start_api "$API_IMAGE"
if ! wait_api; then
  docker logs --tail 30 "$API_CONTAINER"
  docker rm -f "$API_CONTAINER" >/dev/null
  if [ -n "$previous_api" ]; then start_api "$previous_api"; fi
  if [ -n "$previous_worker" ]; then start_worker "$previous_worker"; fi
  echo "Portal API failed its health check. The website was not replaced." >&2
  exit 1
fi

start_worker "$API_IMAGE"
sleep 3
if ! docker exec "$WORKER_CONTAINER" python -c "import sqlite3,time; c=sqlite3.connect('/data/bms_hub.sqlite3'); r=c.execute(\"SELECT value FROM generator_meta WHERE key='heartbeat'\").fetchone(); assert r and time.time()-float(r[0])<30"; then
  docker logs --tail 20 "$WORKER_CONTAINER"
  echo "Document generation worker failed to start." >&2
  exit 1
fi

# The API is internal-only; nginx is the sole published service.
docker stop "$CONTAINER" >/dev/null 2>&1 || true
docker rm "$CONTAINER" >/dev/null 2>&1 || true
if ! docker run -d --name "$CONTAINER" --network "$NETWORK" -p "${PORT}:80" --restart unless-stopped "$IMAGE"; then
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  if [ -n "$previous_site" ]; then
    docker run -d --name "$CONTAINER" --network "$NETWORK" -p "${PORT}:80" --restart unless-stopped "$previous_site"
  fi
  exit 1
fi

echo "Deployment complete: https://www.nxflo.com/bms_integration_hub"
echo "Portal database persists in Docker volume $VOLUME."
