#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/c/Users/ServerAdmin/Documents/GitHub/docker-configs}"
VPN_DELAY_SECONDS="${VPN_DELAY_SECONDS:-60}"
DOCKER_TIMEOUT_SECONDS="${DOCKER_TIMEOUT_SECONDS:-180}"
PATH_TIMEOUT_SECONDS="${PATH_TIMEOUT_SECONDS:-180}"
DOCKHAND_TIMEOUT_SECONDS="${DOCKHAND_TIMEOUT_SECONDS:-180}"
ENV_ID="${DOCKHAND_ENV_ID:-1}"
ARR_STACK_NAME="${ARR_STACK_NAME:-arr_stack}"
ARR_DEPENDENT_CONTAINERS=(qbittorrent prowlarr radarr sonarr byparr cleanuparr seerr)

log() {
  printf '[%(%Y-%m-%d %H:%M:%S %Z)T] %s\n' -1 "$*"
}

wait_for_docker() {
  local deadline=$((SECONDS + DOCKER_TIMEOUT_SECONDS))
  until timeout 10s docker ps >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      log "Docker did not become ready within ${DOCKER_TIMEOUT_SECONDS}s"
      return 1
    fi
    sleep 3
  done
}

wait_for_path() {
  local path="$1"
  local deadline=$((SECONDS + PATH_TIMEOUT_SECONDS))
  until [[ -e "$path" ]]; do
    if (( SECONDS >= deadline )); then
      log "Required path did not become available: $path"
      return 1
    fi
    sleep 3
  done
}

ensure_network() {
  local network="$1"
  if ! docker network inspect "$network" >/dev/null 2>&1; then
    log "Creating missing Docker network: $network"
    docker network create "$network" >/dev/null
  fi
}

compose_up() {
  local project="$1"
  local dir="$2"
  shift 2
  docker compose \
    --project-directory "$dir" \
    -f "$dir/docker-compose.yml" \
    -p "$project" \
    up -d "$@"
}

container_state() {
  local container="$1"
  docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null || true
}

dockhand_api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"

  if [[ -n "$body" ]]; then
    docker exec dockhand curl -fsS \
      -X "$method" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "http://127.0.0.1:3000${path}"
  else
    docker exec dockhand curl -fsS \
      -X "$method" \
      -H "Accept: application/json" \
      "http://127.0.0.1:3000${path}"
  fi
}

wait_for_dockhand_api() {
  local deadline=$((SECONDS + DOCKHAND_TIMEOUT_SECONDS))
  until docker exec dockhand curl -fsS "http://127.0.0.1:3000/api/auth/session" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      log "Dockhand API did not become ready within ${DOCKHAND_TIMEOUT_SECONDS}s"
      return 1
    fi
    sleep 3
  done
}

stop_arr_dependents() {
  local container state

  for container in "${ARR_DEPENDENT_CONTAINERS[@]}"; do
    state="$(container_state "$container")"
    case "$state" in
      running|restarting|paused)
        log "Stopping $container before gluetun-first startup"
        dockhand_api POST "/api/containers/${container}/stop?env=${ENV_ID}" >/dev/null || true
        ;;
      "")
        log "$container does not exist yet; it will be handled by stack startup"
        ;;
      *)
        log "$container is $state"
        ;;
    esac
  done
}

start_container_via_dockhand() {
  local container="$1"
  local state

  state="$(container_state "$container")"
  case "$state" in
    running)
      log "$container is already running"
      ;;
    "")
      log "$container does not exist; cannot start it individually"
      return 2
      ;;
    *)
      log "Starting $container through Dockhand API"
      dockhand_api POST "/api/containers/${container}/start?env=${ENV_ID}" >/dev/null
      ;;
  esac
}

start_arr_dependents() {
  local container missing=0

  for container in "${ARR_DEPENDENT_CONTAINERS[@]}"; do
    start_container_via_dockhand "$container" || missing=1
  done

  if (( missing )); then
    log "One or more Arr containers were missing; starting ${ARR_STACK_NAME} stack through Dockhand API"
    dockhand_api POST "/api/stacks/${ARR_STACK_NAME}/start?env=${ENV_ID}" >/dev/null || \
      dockhand_api POST "/api/stacks/${ARR_STACK_NAME}/deploy?env=${ENV_ID}" '{"pull":false,"build":false,"forceRecreate":false}' >/dev/null
  fi
}

wait_for_container_healthy() {
  local container="$1"
  local timeout="${2:-120}"
  local deadline=$((SECONDS + timeout))
  local status

  while (( SECONDS < deadline )); do
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      log "$container is $status"
      return 0
    fi
    sleep 3
  done

  log "$container did not become healthy within ${timeout}s; continuing after fixed delay"
}

main() {
  log "Waiting for Docker Desktop engine"
  wait_for_docker

  log "Waiting for WSL bind-mount paths"
  wait_for_path "$ROOT/management/docker-compose.yml"

  ensure_network "vpn_stack_brg"
  ensure_network "general_brg"

  log "Starting management stack"
  compose_up "management" "$ROOT/management"
  wait_for_container_healthy "dockhand" 120
  wait_for_dockhand_api

  log "Preparing Arr stack for gluetun-first startup through Dockhand"
  stop_arr_dependents
  start_container_via_dockhand "gluetun" || \
    dockhand_api POST "/api/stacks/${ARR_STACK_NAME}/start?env=${ENV_ID}" >/dev/null
  wait_for_container_healthy "gluetun" 120

  log "Waiting ${VPN_DELAY_SECONDS}s before starting the rest of the VPN stack"
  sleep "$VPN_DELAY_SECONDS"

  log "Starting remaining Arr stack containers through Dockhand"
  start_arr_dependents

  log "Starting web services stack through Dockhand"
  dockhand_api POST "/api/stacks/web_services/start?env=${ENV_ID}" >/dev/null || \
    dockhand_api POST "/api/stacks/web_services/deploy?env=${ENV_ID}" '{"pull":false,"build":false,"forceRecreate":false}' >/dev/null

  log "Startup orchestration complete"
  docker ps --format 'table {{.Names}}\t{{.Status}}'
}

main "$@"
