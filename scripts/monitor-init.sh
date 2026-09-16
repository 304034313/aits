#!/usr/bin/env bash
# AITS 性能监控首次初始化（macOS / Linux Docker）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=monitor-common.sh
source "$(dirname "$0")/monitor-common.sh"

cd "$ROOT"
aits_guard_project_path "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] 未找到 docker 命令，请先安装 Docker Desktop / Docker Engine" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] 未找到 docker compose 插件" >&2
  exit 1
fi

if ! aits_monitor_resolve_docker_network; then
  exit 1
fi

aits_monitor_ensure_runtime_dirs "$ROOT"

if ! aits_monitor_pull_or_use_local "$ROOT"; then
  exit 1
fi

echo "[2/2] docker compose up -d ..."
aits_monitor_prepare_up
aits_monitor_compose_cmd "$ROOT" up -d

aits_monitor_write_marker "$ROOT"

echo ""
echo "[OK] AITS 性能监控栈已启动"
aits_monitor_print_urls
echo ""
echo "开启服务请运行: ./perf-monitor/一键启动性能监控.sh"
