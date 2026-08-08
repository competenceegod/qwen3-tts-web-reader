# Qwen3-TTS Web Reader

This guide installs the unpacked Chrome extension and its local Qwen3-TTS
service. The service is independent of PDFgear and downloads its own model into
the current user's cache.

## Download a release

Open the [Releases page](https://github.com/janycechoice/qwen3-tts-web-reader/releases)
and download exactly one archive:

- `qwen3-tts-web-reader-0.2.0-macos.zip`
- `qwen3-tts-web-reader-0.2.0-windows.zip`
- `qwen3-tts-web-reader-0.2.0-linux.zip`

Optionally download `SHA256SUMS.txt` and verify the archive before extracting
it. Each archive contains an `extension` directory, the local service, a
platform launcher, the license, and a platform-specific `README.md`.

## Install the browser extension

These steps are the same on all three operating systems:

1. Start the local service using the instructions for your operating system
   below and leave its terminal window open.
2. Wait until the launcher displays `http://127.0.0.1:8765/`.
3. Open `chrome://extensions` in Chrome, Edge, Brave, or Chromium.
4. Enable **Developer mode**.
5. Click **Load unpacked**.
6. Select the extracted `extension` directory, not the package's top-level
   directory.
7. Refresh any pages that were already open before the extension was loaded.

Click the extension icon to check whether the local service is reachable.

## macOS installation

The macOS package supports Apple Silicon Macs (M1 or newer). It uses MLX Audio,
which is optimized for Apple Silicon and does not support Intel Macs in this
release.

1. Install `uv`:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Close and reopen Terminal if `uv --version` is not immediately available.
3. Extract the macOS ZIP.
4. Double-click `start-qwen-reader.command`. If Gatekeeper blocks it,
   Control-click the file, select **Open**, and confirm once.
5. Allow the first run to install MLX Audio and download the standalone
   Qwen3-TTS model.

See the [complete macOS guide](platform/macos/README.md) for configuration and
troubleshooting.

## Windows installation

The Windows package supports Windows 10 and 11. An NVIDIA GPU with a compatible
CUDA build of PyTorch is recommended. CPU mode works but is substantially
slower.

1. Open PowerShell and install `uv`:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. Close and reopen PowerShell, then confirm `uv --version` works.
3. Extract the Windows ZIP to a normal writable directory.
4. Double-click `start-qwen-reader.cmd`.
5. Keep the PowerShell window open while using the reader.

See the [complete Windows guide](platform/windows/README.md) for CUDA setup,
configuration, and troubleshooting.

## Linux installation

The Linux package targets mainstream x86_64 distributions. An NVIDIA CUDA GPU
is recommended; CPU mode is available as a slower fallback.

1. Install `uv`:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Install SoX if it is not already present. For Ubuntu or Debian:

   ```bash
   sudo apt update
   sudo apt install sox libsox-fmt-all
   ```

3. Extract the Linux ZIP, open a terminal in the extracted directory, and run:

   ```bash
   chmod +x start-qwen-reader.sh
   ./start-qwen-reader.sh
   ```

See the [complete Linux guide](platform/linux/README.md) for other package
managers, configuration, and troubleshooting.

## Use the reader

1. Open a normal HTTP or HTTPS page.
2. Select text in the page body.
3. Choose **Read selection** for one selection or **Read continuously from
   here** to continue through the article.
4. During continuous reading, press `Space` to pause or resume and `Esc` to
   stop. The floating player also provides speed, pause, and stop controls.

The active sentence is highlighted and automatically scrolled near the center
of the viewport. After a long pause, resuming may regenerate the current
sentence before playback continues.

## Troubleshooting

- **The extension cannot connect:** confirm the launcher is still open and
  visit `http://127.0.0.1:8765/` in the browser. Restart the launcher if needed.
- **The first sentence is slow:** the first launch must install a runtime,
  download the model, and warm it up. Later sessions reuse cached files.
- **Nothing appears after selecting text:** refresh the page after loading or
  reloading the extension. Protected browser pages cannot run the extension.
- **`Space` scrolls instead of pausing:** continuous reading must be active,
  and focus must not be inside an input, text area, or editable element.
- **A `file://` page does not work:** enable **Allow access to file URLs** in
  the extension's details page.

The service intentionally accepts requests only from the local machine. Do not
change it to listen on a public or LAN-facing address.

