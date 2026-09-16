#!/bin/sh
# Docker build: npm — npmmirror first (default), npmjs.org last (VPN/abroad fallback).
set -e

try_registry() {
    registry="$1"
    echo "[npm] trying registry: ${registry}"
    npm ci --registry="${registry}"
}

if [ -n "${NPM_REGISTRY:-}" ]; then
    echo "[npm] using NPM_REGISTRY=${NPM_REGISTRY}"
    try_registry "${NPM_REGISTRY}"
    exit 0
fi

for registry in \
    "https://registry.npmmirror.com" \
    "https://registry.npmjs.org"
do
    if try_registry "${registry}"; then
        echo "[npm] success on ${registry}"
        exit 0
    fi
    echo "[npm] registry ${registry} failed, try next" >&2
done

echo "[npm] install failed on all registries" >&2
exit 1
