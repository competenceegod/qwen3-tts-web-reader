# Qwen3-TTS Web Reader

Qwen3-TTS Web Reader is a local-first Chrome/Chromium extension that reads text
on ordinary web pages with Qwen3-TTS. Select any text and either read the
selection once or continue from that point through the article. The active
sentence is highlighted and kept near the center of the viewport.

The extension sends text only to a local service bound to `127.0.0.1:8765`.
It does not require PDFgear, does not read PDFgear files, and does not upload
page text or generated audio.

## Features

- Read selected text on normal HTTP and HTTPS pages.
- Continue sentence by sentence from the current selection.
- Highlight and automatically center the sentence being spoken.
- Press `Space` to pause or resume continuous reading and `Esc` to stop.
- Resume after long pauses by regenerating the current sentence when Chrome
  has suspended the audio context.
- Adjust playback speed from 0.75x to 1.5x.
- Use a standalone Qwen3-TTS model downloaded to the current user's cache.
- Run on macOS, Windows, and Linux with platform-specific launchers.

## Download and installation

Download the ZIP for your operating system from the
[latest GitHub release](https://github.com/competenceegod/qwen3-tts-web-reader/releases/latest),
extract it, and follow the `README.md` included in that archive.

| Operating system | Runtime | Accelerator | Detailed guide |
| --- | --- | --- | --- |
| macOS | MLX Audio | Apple Silicon | [macOS](browser-extension/platform/macos/README.md) |
| Windows 10/11 | Official `qwen-tts` package | NVIDIA CUDA or CPU | [Windows](browser-extension/platform/windows/README.md) |
| x86_64 Linux | Official `qwen-tts` package | NVIDIA CUDA or CPU | [Linux](browser-extension/platform/linux/README.md) |

For a single cross-platform walkthrough, see
[the extension installation guide](browser-extension/README.md).

## Quick start

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Extract the release ZIP for your operating system.
3. Start the local service with the launcher in the extracted folder.
4. Keep the launcher window open after it displays `http://127.0.0.1:8765/`.
5. Open `chrome://extensions`, enable **Developer mode**, and select
   **Load unpacked**.
6. Choose the extracted `extension` directory, then refresh pages that were
   already open.
7. Select text and choose **Read selection** or **Read continuously from here**.

The first launch installs the platform runtime and downloads the model. This
can take several minutes and several gigabytes of disk space. Later launches
reuse the user-level package and model caches.

## Browser support and limitations

The extension supports current Chrome, Chromium, Edge, Brave, and other
Chromium-based desktop browsers that support Manifest V3. Browser-protected
pages such as `chrome://` URLs and the Chrome Web Store cannot run content
scripts. Cross-origin iframes and the built-in browser PDF viewer are not
supported. To use local `file://` pages, enable **Allow access to file URLs** in
the extension details page.

## Privacy and security

- The service listens only on the loopback interface by default.
- Extension host permissions are limited to `127.0.0.1:8765` and
  `localhost:8765`.
- Release archives do not include models, PDFs, audio samples, credentials, or
  developer-specific absolute paths.
- Models are downloaded by the selected runtime from their normal per-user
  cache and can be used offline after the first successful download.

Do not expose port 8765 to a LAN or the public internet.

## Build from source

Requirements: Git, Python 3.11 or later, `uv`, and Node.js for JavaScript syntax
checks.

```bash
git clone https://github.com/competenceegod/qwen3-tts-web-reader.git
cd qwen3-tts-web-reader
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run python scripts/check_javascript.py
uv run python scripts/check_launchers.py
uv run python scripts/package_extension.py
```

The final command writes reproducible archives and `SHA256SUMS.txt` to `dist/`.
Every push is tested on macOS, Windows, and Linux. A version tag such as
`v0.2.0` runs the full release gate before GitHub publishes the archives.

## Repository layout

```text
browser-extension/          Chrome extension and platform launchers
src/booksite/site/          Local loopback TTS service
scripts/                    Validation and release packaging tools
tests/                      Unit and integration tests
.github/workflows/          Three-platform CI and tagged releases
docs/                       Design specifications and decisions
```

The repository also contains the PDF-to-Docusaurus converter from which the
reader was originally developed. Generated books, model caches, PDFs, and
release archives are intentionally excluded from Git.

## License

The project source is released under the [MIT License](LICENSE). Model weights,
runtime packages, and third-party web content remain subject to their own
licenses and terms.
