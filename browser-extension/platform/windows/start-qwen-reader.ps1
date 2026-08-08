$ErrorActionPreference = "Stop"
$PackageDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = Join-Path $PackageDir "service\local_server.py"
$RestartDelay = if ($env:BOOKSITE_TTS_RESTART_DELAY) { [int]$env:BOOKSITE_TTS_RESTART_DELAY } else { 2 }

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv was not found. Install it from https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

Write-Host "The first run downloads the official Qwen runtime and model."
while ($true) {
    & uv run --no-project --python 3.12 --with "qwen-tts==0.1.1" python $Server `
        --tts-only --tts-backend torch --host 127.0.0.1 --port 8765 --no-open
    $Status = $LASTEXITCODE
    if ($Status -eq 0) { exit 0 }
    if ($Status -in 130, 143) { exit $Status }
    Write-Warning "Qwen3-TTS exited unexpectedly. Restarting in $RestartDelay seconds."
    Start-Sleep -Seconds $RestartDelay
}
