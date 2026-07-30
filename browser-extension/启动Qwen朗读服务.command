#!/bin/sh
set -eu

EXTENSION_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$EXTENSION_DIR/.." && pwd)

if ! command -v uv >/dev/null 2>&1; then
  echo "未找到 uv，无法启动 Qwen3-TTS。请先安装 uv。" >&2
  exit 1
fi

exec uv run --no-project --python 3.12 --with 'mlx-audio==0.4.5' \
  python "$PROJECT_DIR/src/booksite/site/local_server.py" \
  --tts-only --host 127.0.0.1 --port 8765 --no-open
