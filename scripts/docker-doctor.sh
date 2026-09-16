#!/usr/bin/env bash
# Docker Desktop 健康检查（macOS：overlay2 read-only 时脚本无法自愈）
set -euo pipefail

# shellcheck disable=SC1091
source "$(dirname "$0")/bash-compat.sh"
aits_require_bash

echo "===================================================="
echo " AITS Docker Doctor"
echo "===================================================="
echo ""

if ! command -v docker >/dev/null 2>&1; then
  echo "[FAIL] 未找到 docker 命令"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "[FAIL] Docker Desktop 未运行或 daemon 无响应"
  echo "       请先打开 Docker Desktop"
  exit 1
fi

echo "[INFO] Mac 磁盘空间（Docker 虚拟盘依赖宿主机剩余空间）："
df -h / | tail -1
# 可用 GB（整数近似，Bash 3.2）
avail_kb=$(df -k / | tail -1 | awk '{print $4}')
avail_gb=$((avail_kb / 1024 / 1024))
if [ "$avail_gb" -lt 10 ]; then
  echo "[WARN] 可用空间约 ${avail_gb}GB（建议 ≥ 20GB）" >&2
  echo "       不足时常见: overlay2 read-only、celery-worker Exited、监控容器挂掉" >&2
  echo "       请先清理 Mac 磁盘，再 Docker Desktop → Troubleshoot → Clean / Purge data" >&2
fi
echo ""

echo "[INFO] 测试：创建并删除临时容器（检测 overlay2 是否可写）..."
test_name="aits-doctor-rw-test-$$"
if docker run -d --name "$test_name" alpine:latest sleep 2 >/dev/null 2>&1; then
  if docker rm -f "$test_name" >/dev/null 2>&1; then
    echo "[OK] Docker 可正常创建/删除容器"
  else
    echo "[FAIL] 无法删除容器（常见: read-only file system / overlay2 损坏）"
    echo ""
    echo "  必须修复 Docker Desktop（脚本无法绕过）："
    echo "  1. 完全退出 Docker Desktop"
    echo "  2. Docker Desktop → Settings → Troubleshoot → Clean / Purge data"
    echo "     （或 Reset to factory defaults；会清空所有容器/镜像，需重新 docker-init）"
    echo "  3. 确认 Mac 磁盘剩余 ≥ 20GB 后重启 Docker"
    echo "  4. 再运行本脚本，显示 OK 后执行 ./scripts/docker-init.sh"
    exit 1
  fi
else
  echo "[FAIL] 无法创建容器"
  docker run --rm alpine:latest true 2>&1 | tail -5 || true
  exit 1
fi

echo ""
echo "[INFO] 监控相关容器："
docker ps -a --filter name=aits-prometheus --filter name=aits-grafana --filter name=aits-node-exporter \
  --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || true
echo ""
echo "[OK] Docker 基础功能正常，可继续 AITS / 监控脚本"
