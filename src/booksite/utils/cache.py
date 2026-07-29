from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def build_cache_key(
    source_sha256: str,
    page_index: int | None,
    config: dict[str, Any],
    engine: str,
    engine_version: str = "",
    prompt_version: str = "",
) -> str:
    payload = {
        "source_sha256": source_sha256,
        "page_index": page_index,
        "config": config,
        "engine": engine,
        "engine_version": engine_version,
        "prompt_version": prompt_version,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


class CacheStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def stage_path(self, book_id: str, stage: str) -> Path:
        return self.root / book_id / stage / "result.json"

    def read_json(self, book_id: str, stage: str) -> dict[str, Any] | None:
        path = self.stage_path(book_id, stage)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, book_id: str, stage: str, payload: dict[str, Any]) -> Path:
        path = self.stage_path(book_id, stage)
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return path
