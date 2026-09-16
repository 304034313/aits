#!/usr/bin/env bash
# 兼容 Bash 3.2+（macOS 系统默认 bash）

# shellcheck disable=SC1091
source "$(dirname "$0")/bash-compat.sh"
aits_require_bash

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$(dirname "$0")/docker-env.sh"
load_docker_compose_env "$ROOT"

COMPOSE_ENV=(--env-file docker/versions.env)
if [ -f .env.docker ]; then
  COMPOSE_ENV+=(--env-file .env.docker)
fi
docker compose "${COMPOSE_ENV[@]}" down

echo "[OK] AITS Docker 已停止"
