#!/usr/bin/env bash
# AITS 性能监控启动（macOS / Linux Docker）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=monitor-common.sh
source "$(dirname "$0")/monitor-common.sh"

aits_guard_project_path "$ROOT"

MARKER="$(aits_monitor_marker_path "$ROOT")"
if [[ ! -f "$MARKER" ]]; then
  if aits_monitor_prometheus_running; then
    echo "[WARN] 监控容器已在运行，但未找到安装标记（可能安装时 pull 失败中断）。自动补写 marker ..." >&2
    aits_monitor_write_marker "$ROOT"
  else
    echo "[ERROR] 监控未安装。请先运行 ./perf-monitor/一键安装性能监控.sh" >&2
    exit 1
  fi
fi

cd "$ROOT"
aits_monitor_resolve_docker_network

aits_monitor_prepare_up
echo "[INFO] 启动监控栈 ..."
aits_monitor_compose_cmd "$ROOT" up -d

aits_monitor_seed_aits_urls "$ROOT"

echo ""
echo "[OK] 性能监控已启动"
aits_monitor_print_urls
