#!/usr/bin/env bash
# AITS shell 脚本兼容性约定（目标：Bash 3.2+）
#
# 部署环境含 macOS 系统默认 Bash 3.2，脚本须避免 Bash 4+ 专有语法，例如：
#   mapfile / readarray、declare -A（关联数组）、declare -n（nameref）、
#   ${var,,} / ${var^^}、wait -n、|&、&>> 等。
#
# 入口脚本应在 set -euo pipefail 之前或之后尽早调用 aits_require_bash。

aits_require_bash() {
  if [ -z "${BASH_VERSION:-}" ]; then
    echo "[ERROR] 请使用 bash 运行（例如: bash ./scripts/docker-init.sh），不要用 sh" >&2
    exit 1
  fi

  local major="${BASH_VERSINFO[0]:-0}"
  local minor="${BASH_VERSINFO[1]:-0}"
  if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 2 ]; }; then
    echo "[ERROR] 需要 Bash >= 3.2（当前: ${BASH_VERSION}）" >&2
    echo "        macOS 可安装新版: brew install bash" >&2
    echo "        然后用: /opt/homebrew/bin/bash ./scripts/docker-init.sh" >&2
    exit 1
  fi
}

# 项目路径在废纸篓或含空格时，Compose 项目名/卷名会异常，且易触发 Docker 卷创建失败
aits_guard_project_path() {
  local root="${1:-}"

  if [ -z "$root" ]; then
    return 0
  fi

  # 用 grep 判断，避免路径含空格时 case 模式匹配不稳（Bash 3.2）
  if echo "$root" | grep -q '/\.Trash'; then
    echo "" >&2
    echo "[ERROR] 当前在废纸篓里运行，Docker 无法可靠创建监控数据卷。" >&2
    echo "        路径: $root" >&2
    echo "" >&2
    echo "  请按下面做（必须，仅 git pull 不够）：" >&2
    echo "  1. 打开 Finder → 废纸篓 → 选中 lemon-aits →「放回原处」" >&2
    echo "     或拖到固定目录，例如: ~/办公/代码/lemon-aits（路径不要有空格）" >&2
    echo "  2. 终端 cd 到该目录后: git pull" >&2
    echo "  3. 重启 Docker Desktop，再执行 perf-monitor 脚本" >&2
    echo "" >&2
    exit 1
  fi

  if echo "$root" | grep -q ' '; then
    echo "[ERROR] 项目路径含空格，Docker 卷名会异常：" >&2
    echo "        $root" >&2
    echo "        请移到无空格的路径（如 ~/lemon-aits）后再运行。" >&2
    exit 1
  fi
}

# 确认已拉到含「固定监控卷名」的 compose（907bb46 之后）
aits_assert_monitor_compose_ready() {
  local root="${1:-.}"
  local compose_file="${root}/docker-compose.monitor.yml"

  if [ ! -f "$compose_file" ]; then
    echo "[ERROR] 缺少 docker-compose.monitor.yml" >&2
    exit 1
  fi
  if grep -q 'tools/monitor/runtime/docker/prometheus' "$compose_file" 2>/dev/null; then
    return 0
  fi
  if grep -q 'name: aits_monitor_prometheus_data' "$compose_file" 2>/dev/null; then
    echo "[WARN] 监控 compose 为旧版（Docker 命名卷）。请 git pull 或重新下载最新代码包。" >&2
    echo "[WARN] 或在本目录 git pull；验证: grep runtime/docker/prometheus docker-compose.monitor.yml" >&2
    return 0
  fi
  echo "[ERROR] 监控 compose 版本过旧，无法安装。" >&2
  echo "        请 git pull 或重新下载最新代码包。" >&2
  exit 1
}
