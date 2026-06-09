#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${ROOT:-/mnt/c/Users/scott/OneDrive/Documents/GitHub/docker-configs}"
VPN_DELAY_SECONDS="${VPN_DELAY_SECONDS:-60}"
POST_DOCKER_READY_DELAY_SECONDS="${POST_DOCKER_READY_DELAY_SECONDS:-120}"
DOCKER_TIMEOUT_SECONDS="${DOCKER_TIMEOUT_SECONDS:-180}"
PATH_TIMEOUT_SECONDS="${PATH_TIMEOUT_SECONDS:-180}"
DOCKHAND_TIMEOUT_SECONDS="${DOCKHAND_TIMEOUT_SECONDS:-180}"
COMMAND_TIMEOUT_SECONDS="${COMMAND_TIMEOUT_SECONDS:-60}"
INTERNET_TIMEOUT_SECONDS="${INTERNET_TIMEOUT_SECONDS:-300}"
# Probed from inside the dockhand container, so DNS + outbound reachability are
# exercised over the same Docker network path the stacks use. Hostnames (not raw
# IPs) on purpose: this must also catch the DNS-not-ready case seen at boot.
read -r -a INTERNET_PROBE_HOSTS <<< "${INTERNET_PROBE_HOSTS:-https://www.cloudflare.com https://github.com}"
# A single boot log, overwritten on every run, for a quick "what happened last
# boot" view. This is in addition to the wrapper's timestamped per-boot logs.
# The PowerShell wrapper passes the %USERPROFILE%\docker-startup-logs path; this
# default is only used when the script is run directly.
LATEST_LOG_FILE="${LATEST_LOG_FILE:-/mnt/c/Users/scott/docker-startup-logs/latest-boot.log}"
STARTUP_LOCK_FILE="${STARTUP_LOCK_FILE:-/tmp/docker-configs-startup.lock}"
ENV_ID="${DOCKHAND_ENV_ID:-1}"
ARR_STACK_NAME="${ARR_STACK_NAME:-arr_stack}"
ARR_DEPENDENT_CONTAINERS=(qbittorrent prowlarr radarr sonarr byparr cleanuparr seerr optimisarr)
ARR_STACK_CONTAINERS=(gluetun "${ARR_DEPENDENT_CONTAINERS[@]}")

# The stacks bind their data to the S: drive, which WSL exposes via a 9p mount
# (/mnt/s). 9p mounts can be slow/flaky at boot, and if the mount is missing
# Docker silently binds to an empty stub on the WSL rootfs (a small tmpfs),
# which fills up and breaks downloads. Gate startup on the real mount.
DATA_MOUNT_ROOT="${DATA_MOUNT_ROOT:-/mnt/s}"
DATA_MOUNT_TIMEOUT_SECONDS="${DATA_MOUNT_TIMEOUT_SECONDS:-300}"
read -r -a REQUIRED_DATA_PATHS <<< "${REQUIRED_DATA_PATHS:-/mnt/s/downloads/torrents /mnt/s/media /mnt/s/docker/security_inference_stack}"

log() {
  printf '[%(%Y-%m-%d %H:%M:%S %Z)T] %s\n' -1 "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

on_error() {
  local exit_code=$?
  local line_no="${BASH_LINENO[0]:-unknown}"
  log "ERROR: startup failed at line ${line_no} with exit code ${exit_code}"
  log "Recent container state:"
  docker ps -a --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || true
  exit "$exit_code"
}

trap on_error ERR

acquire_lock() {
  exec 9>"$STARTUP_LOCK_FILE"
  if ! flock -n 9; then
    log "Another startup orchestration is already running; exiting"
    exit 0
  fi
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || die "Required command is missing: $command_name"
}

run_with_timeout() {
  local seconds="$1"
  shift
  timeout --preserve-status "${seconds}s" "$@"
}

wait_for_docker() {
  local deadline=$((SECONDS + DOCKER_TIMEOUT_SECONDS))
  until run_with_timeout 10 docker ps >/dev/null 2>&1; do
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

is_real_mount() {
  # True only if $1 is a genuine mountpoint, not an auto-created stub directory
  # sitting on the WSL rootfs (which is how the tmpfs fallback manifests).
  local path="$1"
  if command -v findmnt >/dev/null 2>&1; then
    findmnt --target "$path" >/dev/null 2>&1
  elif command -v mountpoint >/dev/null 2>&1; then
    mountpoint -q "$path"
  else
    awk -v p="$path" '$2 == p { found = 1 } END { exit !found }' /proc/mounts
  fi
}

wait_for_data_mounts() {
  local deadline=$((SECONDS + DATA_MOUNT_TIMEOUT_SECONDS))

  # 1) The 9p drive itself must actually be mounted, not just present as a stub.
  until is_real_mount "$DATA_MOUNT_ROOT"; do
    if (( SECONDS >= deadline )); then
      log "Data drive ${DATA_MOUNT_ROOT} is not mounted (9p mount missing) within ${DATA_MOUNT_TIMEOUT_SECONDS}s"
      return 1
    fi
    log "Waiting for ${DATA_MOUNT_ROOT} 9p mount to become available..."
    sleep 3
  done

  # 2) Each data path the stacks bind to must exist under that mount.
  local path
  for path in "${REQUIRED_DATA_PATHS[@]}"; do
    until [[ -d "$path" ]]; do
      if (( SECONDS >= deadline )); then
        log "Required data path did not appear: $path"
        return 1
      fi
      sleep 3
    done
  done

  # 3) Confirm the drive is writable (9p can mount stale or read-only).
  local probe="${DATA_MOUNT_ROOT}/.stack-startup-write-test.$$"
  if ! ( : > "$probe" ) 2>/dev/null; then
    log "Data drive ${DATA_MOUNT_ROOT} is mounted but not writable"
    return 1
  fi
  rm -f "$probe" 2>/dev/null || true

  log "Data mounts verified on ${DATA_MOUNT_ROOT}: ${REQUIRED_DATA_PATHS[*]}"
}

ensure_network() {
  local network="$1"
  if ! docker network inspect "$network" >/dev/null 2>&1; then
    log "Creating missing Docker network: $network"
    run_with_timeout "$COMMAND_TIMEOUT_SECONDS" docker network create "$network" >/dev/null
  fi
}

start_stack() {
  local stack="$1"
  local _dir="$2"
  local required="${3:-true}"

  log "Starting ${stack} stack through Dockhand"
  if dockhand_api_retry POST "/api/stacks/${stack}/start?env=${ENV_ID}" >/dev/null 2>&1; then
    return 0
  fi

  log "Dockhand start failed for ${stack}; trying deploy"
  if dockhand_api_retry POST "/api/stacks/${stack}/deploy?env=${ENV_ID}" '{"pull":false,"build":false,"forceRecreate":false}' >/dev/null 2>&1; then
    return 0
  fi

  if [[ "$required" == "true" ]]; then
    log "Required stack failed to start through Dockhand API: ${stack}"
    return 1
  fi

  log "Optional stack not started through Dockhand API: ${stack}"
  return 0
}

start_stack_if_needed() {
  local stack="$1"
  local dir="$2"
  local required="${3:-true}"
  shift 3
  local containers=("$@")
  local container state needs_start=0

  if ((${#containers[@]} == 0)); then
    start_stack "$stack" "$dir" "$required"
    return
  fi

  for container in "${containers[@]}"; do
    state="$(container_state "$container")"
    if [[ "$state" != "running" ]]; then
      needs_start=1
      log "${container:-unknown} is ${state:-missing}; ${stack} needs startup"
    fi
  done

  if (( needs_start )); then
    start_stack "$stack" "$dir" "$required"
  else
    log "${stack} stack containers are already running"
  fi
}

ensure_dockhand_running() {
  local state

  state="$(container_state dockhand)"
  case "$state" in
    running)
      log "dockhand is already running"
      ;;
    "")
      die "dockhand container does not exist; create it before relying on startup orchestration"
      ;;
    *)
      log "dockhand is ${state}; starting existing dockhand container"
      run_with_timeout "$COMMAND_TIMEOUT_SECONDS" docker start dockhand >/dev/null
      ;;
  esac
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
    run_with_timeout "$COMMAND_TIMEOUT_SECONDS" docker exec dockhand curl -fsS \
      -X "$method" \
      -H "Accept: application/json" \
      -H "Content-Type: application/json" \
      -d "$body" \
      "http://127.0.0.1:3000${path}"
  else
    run_with_timeout "$COMMAND_TIMEOUT_SECONDS" docker exec dockhand curl -fsS \
      -X "$method" \
      -H "Accept: application/json" \
      "http://127.0.0.1:3000${path}"
  fi
}

dockhand_api_retry() {
  local attempt

  for attempt in 1 2 3; do
    if dockhand_api "$@"; then
      return 0
    fi
    log "Dockhand API call failed on attempt ${attempt}/3: $2"
    sleep 3
  done

  return 1
}

wait_for_dockhand_api() {
  local deadline=$((SECONDS + DOCKHAND_TIMEOUT_SECONDS))
  until run_with_timeout 10 docker exec dockhand curl -fsS "http://127.0.0.1:3000/api/auth/session" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      log "Dockhand API did not become ready within ${DOCKHAND_TIMEOUT_SECONDS}s"
      return 1
    fi
    sleep 3
  done
}

wait_for_internet() {
  # Guard against the Docker Desktop / WSL boot race: containers (and this
  # script) can start before the WSL VM has working outbound DNS and
  # connectivity. In that window gluetun, cloudflare-tunnel and tailscale all
  # fail their startup network checks and exhaust their restart retries, which
  # takes the whole Arr stack down with gluetun. Block here until the network is
  # genuinely usable so everything we start afterwards can reach the internet.
  local deadline=$((SECONDS + INTERNET_TIMEOUT_SECONDS))
  local host all_ok
  while true; do
    all_ok=1
    for host in "${INTERNET_PROBE_HOSTS[@]}"; do
      if ! run_with_timeout 20 docker exec dockhand \
        curl -fsS -o /dev/null --max-time 10 "$host" >/dev/null 2>&1; then
        all_ok=0
        break
      fi
    done
    if (( all_ok )); then
      log "Outbound internet/DNS verified via dockhand (${INTERNET_PROBE_HOSTS[*]})"
      return 0
    fi
    if (( SECONDS >= deadline )); then
      log "Outbound internet/DNS not ready within ${INTERNET_TIMEOUT_SECONDS}s (last failed probe: ${host:-unknown})"
      return 1
    fi
    log "Waiting for outbound internet/DNS (probe failed: ${host:-unknown})..."
    sleep 5
  done
}

container_has_port_bindings() {
  # True when the container requests host port publishing at all.
  local container="$1" count
  count="$(docker inspect --format '{{len .HostConfig.PortBindings}}' "$container" 2>/dev/null || echo 0)"
  [[ "${count:-0}" != "0" ]]
}

container_ports_published() {
  # True when at least one requested port is actually mapped to the host. A
  # boot-race container shows NetworkSettings.Ports entries with empty/null
  # bindings (e.g. {"3000/tcp":[]}), so this prints nothing and returns false.
  local container="$1" actual
  actual="$(docker inspect --format '{{range $p, $b := .NetworkSettings.Ports}}{{if $b}}x{{end}}{{end}}' "$container" 2>/dev/null || true)"
  [[ -n "$actual" ]]
}

restart_container_via_dockhand() {
  local container="$1"
  log "Restarting $container through Dockhand to re-establish its host port mapping"
  dockhand_api_retry POST "/api/containers/${container}/stop?env=${ENV_ID}" >/dev/null || true
  dockhand_api_retry POST "/api/containers/${container}/start?env=${ENV_ID}" >/dev/null
}

remediate_unpublished_ports() {
  # Even when a container is "running" (and reports healthy, because health
  # checks run inside the container), the boot race can leave it with no host
  # port mapping: Docker started it before networking was ready and never
  # established the published ports. Such a container is invisible from the host
  # and LAN. Detect any running container in that state and bounce it through
  # Dockhand so its ports come back, without recreating it or touching its env.
  local container gluetun_fixed=0 running
  running="$(docker ps --format '{{.Names}}' 2>/dev/null || true)"
  while IFS= read -r container; do
    [[ -n "$container" ]] || continue
    # npm is deliberately (re)started last by bring_up_npm_last, which also
    # re-establishes its port mapping, so skip it here.
    [[ "$container" == "npm" ]] && continue
    if container_has_port_bindings "$container" && ! container_ports_published "$container"; then
      log "$container is running but its published ports are not mapped to the host"
      if restart_container_via_dockhand "$container"; then
        [[ "$container" == "gluetun" ]] && gluetun_fixed=1
      else
        log "Failed to remediate port mapping for $container"
      fi
    fi
  done <<< "$running"

  # qbittorrent shares gluetun's network namespace, so restarting gluetun drops
  # its connectivity; bounce qbittorrent too so it re-attaches cleanly.
  if (( gluetun_fixed )) && [[ "$(container_state qbittorrent)" == "running" ]]; then
    restart_container_via_dockhand "qbittorrent" || log "Failed to restart qbittorrent after gluetun remediation"
  fi
}

bring_up_npm_last() {
  # Nginx Proxy Manager resolves its upstreams' Docker IPs when it starts, so it
  # must come up after every other container exists or it can latch onto stale /
  # wrong IPs. It may already be running (restart policy, or the web_services
  # stack start), so restart it here to force a fresh resolve against the final
  # set of container IPs. Done through Dockhand to keep its managed env intact.
  local state
  state="$(container_state npm)"
  case "$state" in
    "")
      log "npm container does not exist; cannot bring it up last"
      return 0
      ;;
    running)
      log "Restarting npm last so it resolves the final container IPs"
      restart_container_via_dockhand npm || log "Failed to restart npm"
      ;;
    *)
      log "Starting npm last so it resolves the final container IPs"
      start_container_via_dockhand npm || log "Failed to start npm"
      ;;
  esac
  wait_for_container_healthy npm 120
}

stop_arr_stack_containers() {
  local container state

  for container in "${ARR_STACK_CONTAINERS[@]}"; do
    state="$(container_state "$container")"
    case "$state" in
      running|restarting|paused)
        log "Stopping Arr stack container through Dockhand API: $container"
        dockhand_api_retry POST "/api/containers/${container}/stop?env=${ENV_ID}" >/dev/null || true
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
      dockhand_api_retry POST "/api/containers/${container}/start?env=${ENV_ID}" >/dev/null
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
    dockhand_api_retry POST "/api/stacks/${ARR_STACK_NAME}/start?env=${ENV_ID}" >/dev/null || \
      dockhand_api_retry POST "/api/stacks/${ARR_STACK_NAME}/deploy?env=${ENV_ID}" '{"pull":false,"build":false,"forceRecreate":false}' >/dev/null
  fi

  sleep 3
  for container in "${ARR_DEPENDENT_CONTAINERS[@]}"; do
    if [[ "$(container_state "$container")" != "running" ]]; then
      log "$container is still not running after initial start; retrying through Dockhand API"
      start_container_via_dockhand "$container" || missing=1
    fi
  done
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

report_container_issues() {
  local bad

  bad="$(
    {
      docker ps -a --filter 'status=exited' --format '{{.Names}}\t{{.Status}}'
      docker ps -a --filter 'status=dead' --format '{{.Names}}\t{{.Status}}'
      docker ps -a --filter 'health=unhealthy' --format '{{.Names}}\t{{.Status}}'
    } 2>/dev/null | sort -u || true
  )"

  if [[ -n "$bad" ]]; then
    log "Containers needing attention:"
    printf '%s\n' "$bad"
  fi
}

main() {
  # Mirror all output to a single boot log that is truncated/overwritten each
  # run, while still streaming to the caller (the wrapper keeps its timestamped
  # copy). tee opens without -a, so the file starts fresh every boot.
  if mkdir -p "$(dirname "$LATEST_LOG_FILE")" 2>/dev/null; then
    exec > >(tee "$LATEST_LOG_FILE") 2>&1
  else
    log "Could not create log directory for ${LATEST_LOG_FILE}; continuing without the single boot log"
  fi
  log "=== docker-configs boot orchestration starting (this file is overwritten each boot) ==="

  require_command docker
  require_command timeout
  require_command flock
  require_command sort
  acquire_lock

  [[ -d "$ROOT" ]] || die "Repo root does not exist: $ROOT"

  log "Waiting for Docker Desktop engine"
  wait_for_docker

  log "Docker is ready; waiting ${POST_DOCKER_READY_DELAY_SECONDS}s before checking running containers"
  sleep "$POST_DOCKER_READY_DELAY_SECONDS"
  log "Containers currently running before orchestration:"
  docker ps --format 'table {{.Names}}\t{{.Status}}'

  ensure_network "vpn_stack_brg"
  ensure_network "general_brg"

  log "Ensuring Dockhand is running after initial boot delay"
  ensure_dockhand_running
  wait_for_container_healthy "dockhand" 120
  wait_for_dockhand_api

  log "Verifying outbound internet/DNS before starting network-dependent stacks"
  wait_for_internet

  log "Waiting for WSL bind-mount paths"
  wait_for_path "$ROOT/management"

  log "Verifying S: data mounts are available before starting data-dependent stacks"
  wait_for_data_mounts

  log "Stopping Arr stack containers through Dockhand before gluetun-first startup"
  stop_arr_stack_containers

  log "Starting gluetun through Dockhand"
  start_container_via_dockhand "gluetun" || die "Cannot enforce gluetun-first startup because the gluetun container is missing"
  wait_for_container_healthy "gluetun" 120

  log "Waiting ${VPN_DELAY_SECONDS}s before starting the rest of the VPN stack"
  sleep "$VPN_DELAY_SECONDS"

  log "Starting remaining Arr stack containers through Dockhand"
  start_arr_dependents

  log "Starting any other configured containers that are not already running"
  start_stack_if_needed "web_services" "$ROOT/web_services" true npm cloudflare-tunnel tailscale-exit-node
  start_stack_if_needed "security_inference_stack" "$ROOT/security_inference_stack" true frigate birdnet-go mosquitto yawamf-monalithic
  start_stack_if_needed "monitoring_management" "$ROOT/monitoring_management" false prometheus grafana snmp-exporter unpoller
  start_stack_if_needed "media_related_stack" "$ROOT/media_related_stack" false plex

  log "Checking for running containers whose published ports were not mapped (boot race)"
  remediate_unpublished_ports

  log "Bringing up Nginx Proxy Manager last so it resolves the final container IPs"
  bring_up_npm_last

  log "Startup orchestration complete"
  docker ps --format 'table {{.Names}}\t{{.Status}}'
  report_container_issues
}

main "$@"
