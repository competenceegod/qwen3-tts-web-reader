# Qwen3-TTS Web Reader — Linux

This package installs an unpacked Chrome extension and a local Qwen3-TTS
service on mainstream x86_64 Linux distributions. It uses the official
`qwen-tts` Python package. An NVIDIA CUDA GPU is recommended; CPU mode is
available as a slower compatibility fallback.

## Requirements

- A current x86_64 Linux distribution
- Chrome, Chromium, Edge, Brave, or another Manifest V3 Chromium browser
- Internet access for the first installation and model download
- Several gigabytes of free disk space for Python packages and model weights
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- SoX and common audio format plugins
- Optional: a supported NVIDIA GPU and current driver

## Install

1. Install `uv`:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Open a new shell and verify it:

   ```bash
   uv --version
   ```

3. Install SoX. Use the command for your distribution:

   ```bash
   # Ubuntu or Debian
   sudo apt update && sudo apt install sox libsox-fmt-all

   # Fedora
   sudo dnf install sox

   # Arch Linux
   sudo pacman -S sox
   ```

4. Extract the Linux ZIP to a permanent directory and open a terminal there.
5. Make the launcher executable and start it:

   ```bash
   chmod +x start-qwen-reader.sh
   ./start-qwen-reader.sh
   ```

6. The first run installs `qwen-tts==0.1.1` and downloads the
   `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` model.
7. Wait until the terminal shows the local service at
   `http://127.0.0.1:8765/`. Leave this terminal open.
8. Open `chrome://extensions`, enable **Developer mode**, and click
   **Load unpacked**.
9. Select the package's `extension` directory and refresh existing tabs.

### Optional NVIDIA CUDA setup

The launcher selects CUDA automatically when PyTorch can detect it. If CUDA is
not available, it uses CPU. Install a PyTorch build compatible with your NVIDIA
driver using the [official PyTorch selector](https://pytorch.org/get-started/locally/),
then restart the service.

## Use the reader

Select text on a normal web page. Choose **Read selection** or **Read
continuously from here**. During continuous reading, press `Space` to pause or
resume and `Esc` to stop. The current sentence is highlighted and kept near the
center of the page.

Stop the service by returning to the terminal and pressing `Control-C`.

## Configuration

Set variables in the shell before starting the launcher:

```bash
export BOOKSITE_TTS_DEVICE=cuda:0  # Use cpu to force CPU mode
export BOOKSITE_TTS_SPEAKER=Ryan
export BOOKSITE_TTS_TORCH_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice
./start-qwen-reader.sh
```

`BOOKSITE_TTS_RESTART_DELAY` controls how many seconds the launcher waits before
restarting the service after an unexpected exit.

## Troubleshooting

- **`uv: command not found`:** open a new shell or apply the PATH change printed
  by the installer.
- **`Permission denied`:** run `chmod +x start-qwen-reader.sh` from the extracted
  package directory.
- **SoX or an audio format is missing:** install the SoX package and your
  distribution's format-plugin package, then restart the launcher.
- **The service uses CPU:** verify `nvidia-smi` and confirm the installed PyTorch
  build reports CUDA support. CPU is the automatic fallback.
- **The extension cannot connect:** keep the launcher terminal open and visit
  `http://127.0.0.1:8765/` in the browser.
- **Speech begins slowly:** CPU generation may be substantially slower than
  CUDA, and the first request also warms the model.

The local service binds only to `127.0.0.1:8765`. Do not expose this port through
a firewall, reverse proxy, container port mapping, or public network interface.
