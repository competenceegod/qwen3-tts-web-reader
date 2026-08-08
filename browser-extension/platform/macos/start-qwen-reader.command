#!/bin/sh
set -eu

PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVER="$PACKAGE_DIR/service/local_server.py"
RESTART_DELAY=${BOOKSITE_TTS_RESTART_DELAY:-2}

if ! command -v uv >/dev/null 2>&1; then
  echo "未找到 uv。请先安装：https://docs.astral.sh/uv/" >&2
  exit 1
fi

echo "首次运行会独立下载 Qwen3-TTS 模型；不需要安装 PDFgear。"
while true; do
  if uv run --no-project --python 3.12 --with 'mlx-audio==0.4.6' \
    python "$SERVER" --tts-only --tts-backend mlx \
    --host 127.0.0.1 --port 8765 --no-open; then
    exit 0
  else
    status=$?
  fi
  case "$status" in
    130|143) exit "$status" ;;
  esac
  echo "Qwen3-TTS 服务异常退出，${RESTART_DELAY} 秒后自动重启…" >&2
  sleep "$RESTART_DELAY"
done
