#!/usr/bin/env bash
# AITS 性能监控停止（macOS / Linux Docker）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=monitor-common.sh
source "$(dirname "$0")/monitor-common.sh"

cd "$ROOT"
aits_guard_project_path "$ROOT"

if [[ -z "${AITS_DOCKER_NETWORK:-}" ]]; then
  aits_monitor_load_network_from_marker "$ROOT" || aits_monitor_resolve_docker_network 2>/dev/null || true
fi

if [[ -n "${AITS_DOCKER_NETWORK:-}" ]]; then
  echo "[INFO] 停止监控栈（compose down，保留 tools/monitor/runtime 数据）..."
  aits_monitor_compose_cmd "$ROOT" down 2>/dev/null || true
else
  echo "[WARN] 未解析到 AITS Docker 网络，改用直接停止监控容器..." >&2
fi

aits_monitor_force_stop

if aits_monitor_any_running; then
  echo "" >&2
  echo "[ERROR] 监控容器仍存在，且 Docker 无法删除（overlay2 read-only）。" >&2
  echo "        一键停止无法彻底清理，需修复 Docker Desktop：" >&2
  echo "        1. 系统设置确认可用磁盘 >= 20GB (df -h /)" >&2
  echo "        2. Docker Desktop -> Troubleshoot -> Clean / Purge data" >&2
  echo "        3. 再执行 ./scripts/docker-init.sh 与 perf-monitor 安装脚本" >&2
  exit 1
fi

echo "[OK] 性能监控已停止（Prometheus / Grafana / node_exporter）"
