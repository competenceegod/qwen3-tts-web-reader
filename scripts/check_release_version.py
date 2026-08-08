#!/usr/bin/env python3
"""Require a Git tag to match the Chrome extension manifest version."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    args = parser.parse_args()
    manifest = json.loads(
        (PROJECT_ROOT / "browser-extension/manifest.json").read_text(encoding="utf-8")
    )
    version = manifest.get("version")
    expected_tag = f"v{version}"
    actual_tag = args.tag.removeprefix("refs/tags/")
    if actual_tag != expected_tag:
        raise SystemExit(
            f"Release tag {actual_tag!r} does not match manifest version {version}; "
            f"expected {expected_tag!r}."
        )
    print(f"Release version verified: {actual_tag}")


if __name__ == "__main__":
    main()
