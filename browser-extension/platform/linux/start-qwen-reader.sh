#!/bin/sh
set -eu

PACKAGE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVER="$PACKAGE_DIR/service/local_server.py"
RESTART_DELAY=${BOOKSITE_TTS_RESTART_DELAY:-2}

if ! command -v uv >/dev/null 2>&1; then
  echo "未找到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

echo "首次运行会下载 Qwen 官方运行库和模型。"
while true; do
  if uv run --no-project --python 3.12 --with 'qwen-tts==0.1.1' \
    python "$SERVER" --tts-only --tts-backend torch \
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
