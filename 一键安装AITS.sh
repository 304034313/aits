#!/usr/bin/env bash
# AITS macOS 一键安装（Docker 路径，首次运行）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] 未检测到 docker，请先安装 Docker Desktop for Mac"
  echo "        https://www.docker.com/products/docker-desktop/"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[ERROR] 未检测到 docker compose，请升级 Docker Desktop"
  exit 1
fi

chmod +x scripts/*.sh 2>/dev/null || true

echo "===================================================="
echo " AITS macOS 一键安装（Docker）"
echo " 项目目录: $ROOT"
echo "===================================================="
echo ""

bash scripts/docker-init.sh
