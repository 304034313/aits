#!/bin/sh
# Docker build: Debian bookworm apt 国内镜像（playwright install-deps 会大量 apt 下载）
set -e

AITS_USE_CHINA_MIRROR="${AITS_USE_CHINA_MIRROR:-1}"
AITS_APT_MIRROR="${AITS_APT_MIRROR:-mirrors.tuna.tsinghua.edu.cn}"

if [ "$AITS_USE_CHINA_MIRROR" = "0" ]; then
  echo "[apt] using default deb.debian.org sources"
  exit 0
fi

echo "[apt] applying mirror: ${AITS_APT_MIRROR}"

for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do
  if [ -f "$f" ]; then
    sed -i \
      -e "s|deb.debian.org|${AITS_APT_MIRROR}|g" \
      -e "s|security.debian.org|${AITS_APT_MIRROR}|g" \
      "$f"
  fi
done
