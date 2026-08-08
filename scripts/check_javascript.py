#!/usr/bin/env python3
"""Run Node's syntax checker over every JavaScript extension source."""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sources = sorted((PROJECT_ROOT / "browser-extension").glob("*.js"))
    if not sources:
        raise SystemExit("No extension JavaScript files found.")
    for source in sources:
        subprocess.run(["node", "--check", str(source)], check=True)


if __name__ == "__main__":
    main()
