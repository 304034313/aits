#!/bin/sh
# Docker build: PyPI mirrors — China sources first (default), official PyPI last.
# AITS_TORCH_VARIANT: cpu (default) | gpu — cpu avoids ~2GB NVIDIA CUDA wheels in Docker.
set -e

AITS_TORCH_VARIANT="${AITS_TORCH_VARIANT:-cpu}"
AITS_TORCH_VARIANT="$(printf '%s' "$AITS_TORCH_VARIANT" | tr '[:upper:]' '[:lower:]')"
case "$AITS_TORCH_VARIANT" in
    gpu|cuda) AITS_TORCH_VARIANT=gpu ;;
    *) AITS_TORCH_VARIANT=cpu ;;
esac

TORCH_VERSION="$(grep -E '^torch==' requirements.txt 2>/dev/null | head -1 | cut -d= -f3 | tr -d '[:space:]' || true)"
TORCH_VERSION="${TORCH_VERSION:-2.8.0}"

REQ_MAIN="requirements.txt"
REQ_REST="/tmp/aits-requirements-no-torch.txt"

prepare_requirements() {
    if [ "$AITS_TORCH_VARIANT" = "cpu" ]; then
        echo "[pip] AITS_TORCH_VARIANT=cpu — install CPU torch ${TORCH_VERSION} from pytorch.org (skip CUDA nvidia_* wheels)"
        pip install "torch==${TORCH_VERSION}" --index-url https://download.pytorch.org/whl/cpu
        grep -v -E '^torch==' requirements.txt >"$REQ_REST" || true
        if [ ! -s "$REQ_REST" ]; then
            echo "[pip] requirements.txt contains only torch; CPU torch install done" >&2
            exit 0
        fi
        REQ_MAIN="$REQ_REST"
    else
        echo "[pip] AITS_TORCH_VARIANT=gpu — full requirements.txt from PyPI mirrors (includes CUDA torch deps)"
        REQ_MAIN="requirements.txt"
    fi
}

try_mirror() {
    index="$1"
    host="$2"
    echo "[pip] trying mirror: ${host}"
    pip install -r "$REQ_MAIN" -i "${index}" --trusted-host "${host}"
}

prepare_requirements

if [ -n "${PIP_INDEX_URL:-}" ] && [ -n "${PIP_TRUSTED_HOST:-}" ]; then
    echo "[pip] using PIP_INDEX_URL=${PIP_INDEX_URL}"
    try_mirror "${PIP_INDEX_URL}" "${PIP_TRUSTED_HOST}"
    exit 0
fi

for pair in \
    "https://mirrors.aliyun.com/pypi/simple/|mirrors.aliyun.com" \
    "https://pypi.mirrors.ustc.edu.cn/simple/|pypi.mirrors.ustc.edu.cn" \
    "https://pypi.tuna.tsinghua.edu.cn/simple|pypi.tuna.tsinghua.edu.cn" \
    "https://pypi.org/simple|pypi.org"
do
    index="${pair%%|*}"
    host="${pair##*|}"
    if try_mirror "${index}" "${host}"; then
        echo "[pip] success on ${host}"
        exit 0
    fi
    echo "[pip] mirror ${host} failed, try next" >&2
done

echo "[pip] install failed on all mirrors" >&2
exit 1
