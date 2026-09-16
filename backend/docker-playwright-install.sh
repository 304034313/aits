#!/bin/sh
# Docker build: Playwright Chromium — apt 国内源 + 浏览器 npmmirror 加速
set -e

AITS_USE_CHINA_MIRROR="${AITS_USE_CHINA_MIRROR:-1}"
PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST:-https://npmmirror.com/mirrors/playwright}"

chmod +x ./docker-apt-mirror.sh
AITS_USE_CHINA_MIRROR="$AITS_USE_CHINA_MIRROR" AITS_APT_MIRROR="${AITS_APT_MIRROR:-}" ./docker-apt-mirror.sh

if [ "$AITS_USE_CHINA_MIRROR" = "0" ]; then
  unset PLAYWRIGHT_DOWNLOAD_HOST
  echo "[playwright] using official browser CDN"
else
  export PLAYWRIGHT_DOWNLOAD_HOST
  echo "[playwright] PLAYWRIGHT_DOWNLOAD_HOST=${PLAYWRIGHT_DOWNLOAD_HOST}"
fi

apt-get update
playwright install-deps chromium
playwright install chromium
rm -rf /var/lib/apt/lists/*
