# Qwen3-TTS Web Reader — macOS

This package installs an unpacked Chrome extension and a local Qwen3-TTS
service. It supports Apple Silicon Macs (M1 or newer) and current Chromium-based
browsers. This release does not support Intel Macs.

The macOS service uses MLX Audio and downloads its own Qwen3-TTS model. PDFgear
is not required, and the launcher does not inspect or reuse PDFgear resources.

## Requirements

- macOS on Apple Silicon (M1, M2, M3, M4, or newer)
- Chrome, Chromium, Edge, Brave, or another Manifest V3 Chromium browser
- Internet access for the first installation and model download
- Several gigabytes of free disk space for Python packages and model weights
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Install

1. Open Terminal and install `uv`:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Close and reopen Terminal, then verify the installation:

   ```bash
   uv --version
   ```

3. Extract the downloaded macOS ZIP to a permanent location. Do not run the
   launcher from inside the ZIP preview.
4. Double-click `start-qwen-reader.command`.
5. If macOS blocks the launcher, Control-click it, choose **Open**, and confirm.
   Alternatively, run it from Terminal:

   ```bash
   chmod +x start-qwen-reader.command
   ./start-qwen-reader.command
   ```

6. The first run installs `mlx-audio==0.4.6` and downloads the standalone
   `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16` model. Keep the Mac
   awake and online until this completes.
7. Wait until the terminal shows the local service at
   `http://127.0.0.1:8765/`. Leave this terminal window open.
8. Open `chrome://extensions`, enable **Developer mode**, and click
   **Load unpacked**.
9. Select the package's `extension` directory and refresh existing tabs.

## Use the reader

Select text on a normal web page. Choose **Read selection** or **Read
continuously from here**. During continuous reading, press `Space` to pause or
resume and `Esc` to stop. The current sentence is highlighted and kept near the
center of the page.

Stop the service by returning to the terminal and pressing `Control-C`.

## Configuration

Set variables in Terminal before launching the script:

```bash
export BOOKSITE_TTS_SPEAKER=Ryan
export BOOKSITE_TTS_MLX_MODEL=mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16
./start-qwen-reader.command
```

`BOOKSITE_TTS_RESTART_DELAY` controls how many seconds the launcher waits before
restarting the service after an unexpected exit.

## Troubleshooting

- **`uv: command not found`:** reopen Terminal after installing `uv`, or follow
  the PATH instructions printed by the installer.
- **The launcher is blocked:** Control-click the launcher and choose **Open**.
  If the archive came from an untrusted source, verify its SHA-256 checksum
  before bypassing Gatekeeper.
- **The model download is slow or interrupted:** restart the launcher. The
  downloader normally resumes from the user cache instead of starting over.
- **The extension reports that the service is unavailable:** keep the launcher
  window open and visit `http://127.0.0.1:8765/` to confirm the service responds.
- **The first sentence is delayed:** allow model warm-up to finish. Later
  sentences and later launches should start faster.
- **An Intel Mac fails to start MLX:** use a supported Apple Silicon Mac; Intel
  is outside this release's compatibility target.

The local service binds only to `127.0.0.1:8765`. Do not expose this port to a
LAN or the public internet.
