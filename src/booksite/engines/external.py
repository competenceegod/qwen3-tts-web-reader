from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

Runner = Callable[..., subprocess.CompletedProcess[str]]


class JsonSubprocessEngine:
    """Adapter for isolated engines that accept an input and emit one JSON file."""

    def __init__(self, name: str, executable: str, timeout_seconds: int = 180) -> None:
        self.name = name
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def parse_page(
        self,
        input_path: str | Path,
        output_path: str | Path,
        log_dir: str | Path,
        runner: Runner = subprocess.run,
    ) -> dict[str, Any]:
        output = Path(output_path)
        logs = Path(log_dir)
        output.parent.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True, exist_ok=True)
        command = [
            self.executable,
            "--input",
            str(input_path),
            "--output",
            str(output),
        ]
        completed = runner(
            command,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=True,
        )
        (logs / f"{self.name}.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (logs / f"{self.name}.stderr.log").write_text(completed.stderr, encoding="utf-8")
        if not output.exists():
            raise RuntimeError(f"{self.name} completed without writing {output}")
        result = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError(f"{self.name} output must be a JSON object")
        return result
