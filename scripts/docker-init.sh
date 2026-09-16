#!/usr/bin/env bash
# AITS Docker 首次初始化（macOS / Linux）
# 兼容 Bash 3.2+（macOS 系统默认 bash）

# shellcheck disable=SC1091
source "$(dirname "$0")/bash-compat.sh"
aits_require_bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
aits_guard_project_path "$ROOT"

# shellcheck disable=SC1091
source "$(dirname "$0")/docker-env.sh"
load_docker_compose_env "$ROOT"

if [ ! -f .env.docker ]; then
  if [ -f .env.docker.example ]; then
    cp .env.docker.example .env.docker
    echo "[INFO] 已创建 .env.docker，请按需修改 DJANGO_SECRET_KEY 后重新运行"
  else
    echo "[ERROR] 缺少 .env.docker.example" >&2
    exit 1
  fi
fi

COMPOSE_ENV=(--env-file docker/versions.env)
if [ -f .env.docker ]; then
  COMPOSE_ENV+=(--env-file .env.docker)
fi

echo "[1/3] docker compose build（镜像版本见 docker/versions.env）..."
echo "[INFO] AITS_TORCH_VARIANT 默认 cpu（.env.docker）；gpu 需安装前改 .env.docker 并 build --no-cache"
echo "[INFO] pip/npm/apt/Playwright 默认国内镜像（清华 apt、npmmirror 等），失败自动回退官方源"
echo "[INFO] 海外 VPN 自测时国内源可能 403，属正常，会自动改用 pypi.org / npmjs.org"
echo "[INFO] 国内网络建议关闭 VPN；若报 reg-mirror lookup 失败，请清理 Docker Desktop 失效镜像加速"
docker compose "${COMPOSE_ENV[@]}" build

echo "[2/3] migrate ..."
docker compose "${COMPOSE_ENV[@]}" run --rm backend python manage.py migrate --noinput

echo "[3/3] docker compose up -d ..."
docker compose "${COMPOSE_ENV[@]}" up -d

echo ""
echo "===================================================="
echo " AITS Docker 已启动"
echo " 访问: http://localhost:8080"
echo " 管理后台: http://localhost:8080/admin/"
echo ""
echo " 首次请创建管理员:"
echo "   docker compose exec backend python manage.py createsuperuser"
echo "===================================================="
