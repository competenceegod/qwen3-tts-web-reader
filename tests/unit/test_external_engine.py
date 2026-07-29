import json
import subprocess
from pathlib import Path

from booksite.engines.external import JsonSubprocessEngine


def test_external_engine_uses_json_contract_and_persists_logs(tmp_path: Path) -> None:
    output_path = tmp_path / "page.json"

    def fake_runner(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert command[-1] == str(output_path)
        assert capture_output and text and check
        assert timeout == 12
        output_path.write_text(json.dumps({"markdown": "# Parsed"}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "engine stdout", "engine stderr")

    engine = JsonSubprocessEngine("ovisocr2", "ovisocr2-parse", timeout_seconds=12)
    result = engine.parse_page(
        tmp_path / "page.png",
        output_path,
        tmp_path / "logs",
        runner=fake_runner,
    )

    assert result["markdown"] == "# Parsed"
    assert (tmp_path / "logs" / "ovisocr2.stdout.log").read_text() == "engine stdout"
    assert (tmp_path / "logs" / "ovisocr2.stderr.log").read_text() == "engine stderr"
