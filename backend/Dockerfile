# 版本基准：tools/installers/versions.json → docker.python_image
ARG PYTHON_IMAGE=python:3.12-bookworm
# cpu = 默认 Docker 部署（无 GPU）；gpu = 高级，需宿主机 NVIDIA
ARG AITS_TORCH_VARIANT=cpu
# 国内构建加速：apt + Playwright 浏览器；海外可设 AITS_USE_CHINA_MIRROR=0
ARG AITS_USE_CHINA_MIRROR=1
ARG AITS_APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
FROM ${PYTHON_IMAGE}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    AITS_TORCH_VARIANT=${AITS_TORCH_VARIANT}

WORKDIR /app/backend

COPY docker-apt-mirror.sh docker-pip-install.sh docker-playwright-install.sh requirements.txt ./
RUN chmod +x docker-apt-mirror.sh docker-pip-install.sh docker-playwright-install.sh && \
    AITS_USE_CHINA_MIRROR=${AITS_USE_CHINA_MIRROR} AITS_APT_MIRROR=${AITS_APT_MIRROR} ./docker-apt-mirror.sh && \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN ./docker-pip-install.sh

RUN AITS_USE_CHINA_MIRROR=${AITS_USE_CHINA_MIRROR} \
    AITS_APT_MIRROR=${AITS_APT_MIRROR} \
    PLAYWRIGHT_DOWNLOAD_HOST=${PLAYWRIGHT_DOWNLOAD_HOST} \
    ./docker-playwright-install.sh

COPY . .

RUN chmod +x /app/backend/docker-entrypoint.sh

ENV AITS_PLAYWRIGHT_HEADLESS=1

ENTRYPOINT ["/app/backend/docker-entrypoint.sh"]
