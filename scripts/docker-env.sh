#!/usr/bin/env bash
# 供 docker-init/up/down 等脚本 source：加载 versions.env 并为镜像名设兜底默认值
# 仅被 source，勿直接执行；入口脚本须先 aits_require_bash（见 bash-compat.sh）

load_docker_compose_env() {
  local root="${1:-.}"

  if [ -f "${root}/docker/versions.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "${root}/docker/versions.env"
    set +a
  fi

  # 空字符串也回退到默认，避免 compose 把 NGINX_IMAGE= 传给 Dockerfile 导致 FROM 失败
  export PYTHON_IMAGE="${PYTHON_IMAGE:-python:3.12-bookworm}"
  export NODE_IMAGE="${NODE_IMAGE:-node:24.16.0-bookworm}"
  export REDIS_IMAGE="${REDIS_IMAGE:-redis:5.0.14-alpine}"
  export NGINX_IMAGE="${NGINX_IMAGE:-nginx:1.27-alpine}"
  export AITS_TORCH_VARIANT="${AITS_TORCH_VARIANT:-cpu}"
}

# compose 的 env_file 指向 .env.docker；缺失时 compose exec 会失败（容器已在跑时仍常见）
ensure_docker_env_file() {
  local root="${1:-.}"

  if [ -f "${root}/.env.docker" ]; then
    return 0
  fi
  if [ -f "${root}/.env.docker.example" ]; then
    cp "${root}/.env.docker.example" "${root}/.env.docker"
    echo "[INFO] 已从 .env.docker.example 创建 .env.docker"
    return 0
  fi
  echo "[WARN] 缺少 .env.docker 与 .env.docker.example" >&2
  return 1
}
