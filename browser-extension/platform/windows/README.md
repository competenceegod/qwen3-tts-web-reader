# Qwen3-TTS Web Reader — Windows

This package installs an unpacked Chrome extension and a local Qwen3-TTS
service on Windows 10 or 11. It uses the official `qwen-tts` Python package.
An NVIDIA CUDA GPU is recommended; CPU mode is available but significantly
slower.

## Requirements

- 64-bit Windows 10 or 11
- Chrome, Edge, Brave, or another Manifest V3 Chromium browser
- Internet access for the first installation and model download
- Several gigabytes of free disk space for Python packages and model weights
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Optional: a supported NVIDIA GPU and current driver

## Install

1. Open PowerShell and install `uv`:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. Close and reopen PowerShell, then verify the installation:

   ```powershell
   uv --version
   ```

3. Extract the Windows ZIP to a permanent, writable directory. Do not run the
   launcher from inside File Explorer's ZIP view.
4. Double-click `start-qwen-reader.cmd`. The command file invokes
   `start-qwen-reader.ps1` with a process-scoped execution-policy bypass; it
   does not change the system execution policy.
5. The first run installs `qwen-tts==0.1.1` and downloads the
   `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` model.
6. Wait until the PowerShell window shows the local service at
   `http://127.0.0.1:8765/`. Leave this window open.
7. Open `chrome://extensions`, enable **Developer mode**, and click
   **Load unpacked**.
8. Select the package's `extension` directory and refresh existing tabs.

### Optional NVIDIA CUDA setup

The launcher uses CUDA automatically when the installed PyTorch runtime can
detect it. If the service falls back to CPU despite having an NVIDIA GPU,
install a PyTorch build compatible with your driver by following the
[official PyTorch installation selector](https://pytorch.org/get-started/locally/),
then restart the launcher. Do not install an arbitrary CUDA build that does not
match your driver.

## Use the reader

Select text on a normal web page. Choose **Read selection** or **Read
continuously from here**. During continuous reading, press `Space` to pause or
resume and `Esc` to stop. The current sentence is highlighted and kept near the
center of the page.

Stop the service by closing the PowerShell window or pressing `Control-C`.

## Configuration

Set variables in PowerShell before starting the `.ps1` launcher directly:

```powershell
$env:BOOKSITE_TTS_DEVICE = "cuda:0"  # Use "cpu" to force CPU mode
$env:BOOKSITE_TTS_SPEAKER = "Ryan"
$env:BOOKSITE_TTS_TORCH_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
.\start-qwen-reader.ps1
```

`BOOKSITE_TTS_RESTART_DELAY` controls how many seconds the launcher waits before
restarting the service after an unexpected exit.

## Troubleshooting

- **`uv` is not recognized:** close and reopen PowerShell after installation,
  then follow the PATH instructions printed by the `uv` installer.
- **PowerShell blocks the script:** start `start-qwen-reader.cmd`, which applies
  a bypass only to that process. Do not weaken the machine-wide policy.
- **Windows Security quarantines a file:** verify the release checksum and scan
  the extracted package. Do not disable antivirus protection globally.
- **The service uses CPU:** confirm `nvidia-smi` works and that your installed
  PyTorch build reports CUDA support. CPU is the automatic compatibility
  fallback.
- **The extension cannot connect:** leave the PowerShell window open and visit
  `http://127.0.0.1:8765/` in the browser.
- **Speech starts slowly:** CPU generation can be much slower than CUDA. The
  first request also includes model warm-up.

The local service binds only to `127.0.0.1:8765`. Do not open this port in
Windows Firewall for public or LAN access.
