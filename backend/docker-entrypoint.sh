#!/bin/sh
set -e

if [ -n "$REDIS_URL" ]; then
  host=$(python - <<'PY'
import os
from urllib.parse import urlparse
u = urlparse(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
print(u.hostname or "redis")
PY
)
  port=$(python - <<'PY'
import os
from urllib.parse import urlparse
u = urlparse(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
print(u.port or 6379)
PY
)
  echo "[entrypoint] waiting for redis at ${host}:${port}..."
  i=0
  while [ "$i" -lt 60 ]; do
    if python -c "import socket; s=socket.socket(); s.settimeout(1); s.connect(('${host}', ${port})); s.close()" 2>/dev/null; then
      echo "[entrypoint] redis is ready"
      break
    fi
    i=$((i + 1))
    if [ "$i" -eq 60 ]; then
      echo "[entrypoint] redis not ready after 60s" >&2
      exit 1
    fi
    sleep 1
  done
fi

if [ -n "$SQLITE_DB_PATH" ]; then
  persist_dir=$(dirname "$SQLITE_DB_PATH")
  mkdir -p "$persist_dir"
  if [ -n "$MEDIA_ROOT" ]; then
    mkdir -p "$MEDIA_ROOT"
  fi
  if [ -n "$CHROMA_PERSIST_DIR" ]; then
    mkdir -p "$CHROMA_PERSIST_DIR"
  fi
fi

exec "$@"
