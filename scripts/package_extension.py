#!/usr/bin/env python3
"""Build deterministic, self-contained platform archives for the browser reader."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_ROOT = PROJECT_ROOT / "browser-extension"
SERVICE_SOURCE = PROJECT_ROOT / "src/booksite/site/local_server.py"
LICENSE_SOURCE = PROJECT_ROOT / "LICENSE"
FIXED_TIMESTAMP = (2026, 1, 1, 0, 0, 0)
PLATFORM_LAUNCHERS = {
    "macos": ("start-qwen-reader.command",),
    "windows": ("start-qwen-reader.cmd", "start-qwen-reader.ps1"),
    "linux": ("start-qwen-reader.sh",),
}
EXTENSION_FILES = (
    "audio-engine.js",
    "background.js",
    "content.css",
    "content.js",
    "manifest.json",
    "offscreen.html",
    "offscreen.js",
    "page-reader.js",
    "popup.html",
    "popup.js",
    "reading-queue.js",
)


def _read_regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Release input must be a regular file: {path}")
    return path.read_bytes()


def _archive_entry(path: str, payload: bytes, *, executable: bool = False) -> zipfile.ZipInfo:
    pure_path = PurePosixPath(path)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ValueError(f"Unsafe archive path: {path}")
    info = zipfile.ZipInfo(str(pure_path), FIXED_TIMESTAMP)
    info.create_system = 3
    mode = stat.S_IFREG | (0o755 if executable else 0o644)
    info.external_attr = mode << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _platform_files(platform: str, version: str) -> list[tuple[str, bytes, bool]]:
    root = f"qwen3-tts-web-reader-{version}-{platform}"
    files: list[tuple[str, bytes, bool]] = []
    for filename in EXTENSION_FILES:
        source = EXTENSION_ROOT / filename
        files.append((f"{root}/extension/{filename}", _read_regular_file(source), False))
    files.extend(
        (
            (f"{root}/service/local_server.py", _read_regular_file(SERVICE_SOURCE), False),
            (
                f"{root}/README.md",
                _read_regular_file(EXTENSION_ROOT / "platform" / platform / "README.md"),
                False,
            ),
            (f"{root}/LICENSE", _read_regular_file(LICENSE_SOURCE), False),
        )
    )
    for launcher in PLATFORM_LAUNCHERS[platform]:
        payload = _read_regular_file(EXTENSION_ROOT / "platform" / platform / launcher)
        if platform == "windows":
            payload = payload.decode("utf-8").replace("\r\n", "\n").replace("\n", "\r\n").encode()
        files.append((f"{root}/{launcher}", payload, platform != "windows"))
    return files


def build_archives(output_dir: Path) -> list[Path]:
    manifest = json.loads(_read_regular_file(EXTENSION_ROOT / "manifest.json"))
    version = manifest["version"]
    if not isinstance(version, str) or not version:
        raise ValueError("manifest version must be a non-empty string")
    output_dir.mkdir(parents=True, exist_ok=True)
    archives: list[Path] = []
    for platform in PLATFORM_LAUNCHERS:
        archive = output_dir / f"qwen3-tts-web-reader-{version}-{platform}.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for name, payload, executable in _platform_files(platform, version):
                package.writestr(_archive_entry(name, payload, executable=executable), payload)
        archives.append(archive)
    checksums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in archives
    )
    (output_dir / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8", newline="\n")
    return archives


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "dist")
    args = parser.parse_args()
    for archive in build_archives(args.output_dir.resolve()):
        print(archive)


if __name__ == "__main__":
    main()
