#!/usr/bin/env bash
# AITS performance monitor helpers (macOS / Linux Docker)
# 兼容 Bash 3.2+（macOS 系统默认 bash）；勿使用 mapfile 等 Bash 4+ 语法

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/bash-compat.sh"
aits_require_bash

set -euo pipefail

MONITOR_MARKER_REL="tools/monitor/runtime/.aits-monitor-installed"
MONITOR_COMPOSE_FILE="docker-compose.monitor.yml"
# 固定 compose 项目名，避免目录名（含废纸篓、空格）污染卷名
MONITOR_COMPOSE_PROJECT="aits-monitor"

aits_monitor_required_images() {
  printf '%s\n' \
    "${PROMETHEUS_IMAGE:-prom/prometheus:v3.12.0}" \
    "${GRAFANA_IMAGE:-grafana/grafana:13.0.2}" \
    "${NODE_EXPORTER_IMAGE:-prom/node-exporter:v1.9.0}"
}

aits_monitor_pull_or_use_local() {
  local root="$1"
  local env_file="${root}/docker/monitor-versions.env"
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$env_file"
    set +a
  fi

  echo "[1/2] docker compose pull（镜像版本见 docker/monitor-versions.env）..."
  if aits_monitor_compose_cmd "$root" pull; then
    return 0
  fi

  echo "[WARN] docker compose pull 失败（常见: Docker Desktop read-only / 磁盘满）。" >&2
  echo "[WARN] 将检查本地是否已有监控镜像..." >&2
  local img missing=0
  while IFS= read -r img; do
    [ -n "$img" ] || continue
    if docker image inspect "$img" >/dev/null 2>&1; then
      echo "[INFO] 本地已有: $img"
    else
      echo "[ERROR] 本地缺少镜像: $img" >&2
      missing=1
    fi
  done < <(aits_monitor_required_images)

  if [ "$missing" -ne 0 ]; then
    echo "[ERROR] 无法 pull 且本地镜像不全。请重启 Docker Desktop，检查磁盘空间后重试。" >&2
    echo "        Docker Desktop → Troubleshoot → Restart / Clean / Purge data（最后手段）" >&2
    return 1
  fi
  echo "[INFO] 本地镜像齐全，跳过 pull，继续 up -d"
  return 0
}

aits_monitor_prometheus_running() {
  docker ps --filter name=aits-prometheus --filter status=running --format '{{.Names}}' | grep -qx 'aits-prometheus'
}

aits_monitor_ensure_runtime_dirs() {
  local root="$1"
  local prom_dir="${root}/tools/monitor/runtime/docker/prometheus"
  local graf_dir="${root}/tools/monitor/runtime/docker/grafana"
  mkdir -p "$prom_dir" "$graf_dir"
  chmod 777 "$prom_dir" "$graf_dir" 2>/dev/null || true
}

aits_monitor_force_stop() {
  local name found=0
  for name in aits-prometheus aits-grafana aits-node-exporter; do
    if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
      echo "[INFO] 移除监控容器: ${name}"
      if ! docker rm -f "$name" 2>/dev/null; then
        echo "[WARN] 无法移除 ${name} (常见: overlay2 read-only / 磁盘不足)" >&2
        echo "[WARN] 请清理 Mac 磁盘至 20GB+ 后 Docker Desktop -> Troubleshoot -> Clean / Purge data" >&2
      fi
      found=1
    fi
  done
  if [ "$found" -eq 0 ]; then
    echo "[INFO] 无残留监控容器"
  fi
}

aits_monitor_any_running() {
  local name
  for name in aits-prometheus aits-grafana aits-node-exporter; do
    if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
      return 0
    fi
  done
  return 1
}

# compose 项目名与旧目录不一致时，down 删不掉固定 container_name；up 前必须先清理
aits_monitor_prepare_up() {
  local has=0
  if aits_monitor_any_running; then
    has=1
  fi
  if [ "$has" -eq 1 ]; then
    echo "[INFO] 发现同名监控容器（可能来自旧目录 lemon-aits），启动前先移除 ..."
    aits_monitor_force_stop
  fi
}

aits_monitor_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$(dirname "$script_dir")" && pwd
}

aits_monitor_resolve_docker_network() {
  local network=""
  if docker ps -a --format '{{.Names}}' | grep -qx 'aits-celery-worker'; then
    network="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' aits-celery-worker 2>/dev/null || true)"
  fi
  if [[ -z "$network" ]] && docker ps -a --format '{{.Names}}' | grep -qx 'aits-backend'; then
    network="$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' aits-backend 2>/dev/null || true)"
  fi
  if [[ -z "$network" ]]; then
    echo "[ERROR] 未找到 AITS Docker 网络（aits-backend / aits-celery-worker 未在运行）。" >&2
    echo "        请先在同一项目目录执行:" >&2
    echo "          ./scripts/docker-up.sh" >&2
    echo "        若从未部署过，执行 ./scripts/docker-init.sh" >&2
    echo "        验证: docker ps | grep aits-backend" >&2
    return 1
  fi
  export AITS_DOCKER_NETWORK="$network"
  echo "[INFO] AITS Docker network: $AITS_DOCKER_NETWORK"
}

aits_monitor_aits_running() {
  docker ps --filter name=aits-backend --filter status=running --format '{{.Names}}' | grep -qx 'aits-backend'
}

aits_monitor_backend_running() {
  docker ps --filter name=aits-backend --filter status=running --format '{{.Names}}' | grep -qx 'aits-backend'
}

aits_monitor_marker_path() {
  local root="$1"
  echo "${root}/${MONITOR_MARKER_REL}"
}

aits_monitor_write_marker() {
  local root="$1"
  local marker
  marker="$(aits_monitor_marker_path "$root")"
  mkdir -p "$(dirname "$marker")"
  {
    printf 'installed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'platform=docker\n'
    if [[ -n "${AITS_DOCKER_NETWORK:-}" ]]; then
      printf 'docker_network=%s\n' "$AITS_DOCKER_NETWORK"
    fi
  } >"$marker"
}

aits_monitor_load_network_from_marker() {
  local root="$1"
  local marker
  marker="$(aits_monitor_marker_path "$root")"
  if [[ -f "$marker" ]]; then
    local saved
    saved="$(grep -E '^docker_network=' "$marker" 2>/dev/null | head -1 | cut -d= -f2- || true)"
    if [[ -n "$saved" ]]; then
      export AITS_DOCKER_NETWORK="$saved"
      return 0
    fi
  fi
  return 1
}

aits_monitor_compose_cmd() {
  local root="$1"
  shift
  aits_assert_monitor_compose_ready "$root"
  aits_monitor_ensure_runtime_dirs "$root"
  if [[ -n "${AITS_DOCKER_NETWORK:-}" ]]; then
    export AITS_DOCKER_NETWORK
  fi
  (
    cd "$root"
    docker compose -p "$MONITOR_COMPOSE_PROJECT" -f "$MONITOR_COMPOSE_FILE" \
      --env-file "${root}/docker/monitor-versions.env" \
      "$@"
  )
}

aits_monitor_aits_compose_cmd() {
  local root="$1"
  shift
  # shellcheck disable=SC1091
  source "$(dirname "${BASH_SOURCE[0]}")/docker-env.sh"
  ensure_docker_env_file "$root" || true
  local -a aits_env=(--env-file docker/versions.env)
  if [[ -f "${root}/.env.docker" ]]; then
    aits_env+=(--env-file .env.docker)
  fi
  (
    cd "$root"
    docker compose "${aits_env[@]}" "$@"
  )
}

aits_monitor_backend_exec() {
  # docker exec 无 -T（-T 仅 docker compose exec 支持）；非交互执行 manage.py 无需分配 TTY
  docker exec aits-backend "$@"
}

aits_monitor_seed_aits_urls() {
  local root="$1"
  if ! aits_monitor_backend_running; then
    echo "[WARN] aits-backend 未运行，跳过 seed_monitor_config（请先 ./scripts/docker-up.sh）" >&2
    return 0
  fi
  echo "[INFO] refresh_prom_sd + seed_monitor_config ..."
  # 用 docker exec 避免 compose 因宿主机缺少 .env.docker 而拒绝 exec（容器已在运行）
  aits_monitor_backend_exec python manage.py refresh_prom_sd || \
    echo "[WARN] refresh_prom_sd failed" >&2
  aits_monitor_backend_exec python manage.py seed_monitor_config --sync-defaults || \
    echo "[WARN] seed_monitor_config failed" >&2
}

aits_monitor_print_urls() {
  local host="${AITS_MONITOR_HOST:-${AITS_CLASSROOM_HOST:-localhost}}"
  host="${host%%:*}"
  echo ""
  echo "===================================================="
  echo " Prometheus targets: http://${host}:9090/targets"
  echo " Grafana:            http://${host}:3000"
  echo " AITS iframe:        http://${host}:3000/d/aits-perf/aits-performance?kiosk=1"
  echo "===================================================="
}
