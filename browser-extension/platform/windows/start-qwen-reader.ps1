$ErrorActionPreference = "Stop"
$PackageDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = Join-Path $PackageDir "service\local_server.py"
$RestartDelay = if ($env:BOOKSITE_TTS_RESTART_DELAY) { [int]$env:BOOKSITE_TTS_RESTART_DELAY } else { 2 }

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

Write-Host "首次运行会下载 Qwen 官方运行库和模型。"
while ($true) {
    & uv run --no-project --python 3.12 --with "qwen-tts==0.1.1" python $Server `
        --tts-only --tts-backend torch --host 127.0.0.1 --port 8765 --no-open
    $Status = $LASTEXITCODE
    if ($Status -eq 0) { exit 0 }
    if ($Status -in 130, 143) { exit $Status }
    Write-Warning "Qwen3-TTS 服务异常退出，$RestartDelay 秒后自动重启…"
    Start-Sleep -Seconds $RestartDelay
}
