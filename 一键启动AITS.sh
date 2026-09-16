#!/usr/bin/env bash
# AITS macOS 一键启动（Docker 路径，日常运行）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] 未检测到 docker，请先安装 Docker Desktop for Mac"
  exit 1
fi

chmod +x scripts/*.sh 2>/dev/null || true

echo "===================================================="
echo " AITS macOS 一键启动"
echo "===================================================="
echo ""

bash scripts/docker-up.sh
