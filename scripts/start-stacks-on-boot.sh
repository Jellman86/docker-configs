#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/c/Users/ServerAdmin/Documents/GitHub/docker-configs}"
VPN_DELAY_SECONDS="${VPN_DELAY_SECONDS:-60}"
DOCKER_TIMEOUT_SECONDS="${DOCKER_TIMEOUT_SECONDS:-180}"
PATH_TIMEOUT_SECONDS="${PATH_TIMEOUT_SECONDS:-180}"

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
  wait_for_path "$ROOT/arr_vpn_stack/docker-compose.yml"
  wait_for_path "$ROOT/security_inference_stack/docker-compose.yml"
  wait_for_path "$ROOT/web_services/docker-compose.yml"
  wait_for_path "/home/jellman86/docker/arrstack/gluetun"
  wait_for_path "/home/jellman86/docker/security_inference_stack/mosquitto/config/mosquitto.conf"
  wait_for_path "/home/jellman86/docker/security_inference_stack/YA-WAMF/config/config.json"
  wait_for_path "/home/jellman86/docker/security_inference_stack/YA-WAMF/data"
  wait_for_path "/mnt/d/downloads/torrents"
  wait_for_path "/mnt/d/media"

  ensure_network "vpn_stack_brg"
  ensure_network "general_brg"

  log "Starting gluetun first"
  compose_up "arr_stack_vpn" "$ROOT/arr_vpn_stack" gluetun
  wait_for_container_healthy "gluetun" 120

  log "Waiting ${VPN_DELAY_SECONDS}s before starting the rest of the VPN stack"
  sleep "$VPN_DELAY_SECONDS"

  log "Starting remaining VPN stack services"
  compose_up "arr_stack_vpn" "$ROOT/arr_vpn_stack" \
    qbittorrent prowlarr radarr sonarr flaresolverr seerr

  log "Starting web services stack"
  compose_up "web_services" "$ROOT/web_services"

  log "Starting security inference stack"
  compose_up "security_inference_stack" "$ROOT/security_inference_stack"

  log "Startup orchestration complete"
  docker ps --format 'table {{.Names}}\t{{.Status}}'
}

main "$@"
