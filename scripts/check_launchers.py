#!/usr/bin/env python3
"""Syntax-check the platform launchers available on the current runner."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_ROOT = PROJECT_ROOT / "browser-extension/platform"


def _check_posix() -> None:
    shell = shutil.which("sh")
    if shell is None:
        raise SystemExit("sh is required to validate POSIX launchers")
    launchers = [
        PLATFORM_ROOT / "macos/start-qwen-reader.command",
        PLATFORM_ROOT / "linux/start-qwen-reader.sh",
        PROJECT_ROOT / "browser-extension/启动Qwen朗读服务.command",
    ]
    for launcher in launchers:
        subprocess.run([shell, "-n", str(launcher)], check=True)


def _check_windows() -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        raise SystemExit("PowerShell is required to validate the Windows launcher")
    launcher = PLATFORM_ROOT / "windows/start-qwen-reader.ps1"
    command = (
        "$tokens=$null; $errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{launcher}',"
        "[ref]$tokens,[ref]$errors) > $null; "
        "if ($errors.Count -gt 0) { $errors | Write-Error; exit 1 }"
    )
    subprocess.run([powershell, "-NoProfile", "-Command", command], check=True)


def main() -> None:
    if sys.platform == "win32":
        _check_windows()
    else:
        _check_posix()


if __name__ == "__main__":
    main()
