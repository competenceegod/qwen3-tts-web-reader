import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_ci_runs_quality_gates_on_all_supported_operating_systems() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    for runner in ("ubuntu-latest", "macos-latest", "windows-latest"):
        assert runner in workflow
    assert "permissions:" in workflow
    assert "contents: read" in workflow
    assert "astral-sh/setup-uv@v9.0.0" in workflow
    assert "uv run --frozen pytest" in workflow
    assert "uv run --frozen ruff check ." in workflow
    assert "scripts/check_javascript.py" in workflow
    assert "scripts/check_launchers.py" in workflow
    assert "scripts/package_extension.py" in workflow


def test_tag_release_rechecks_version_and_uploads_only_audited_artifacts() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "tags:" in workflow
    assert "'v*'" in workflow
    assert "contents: write" in workflow
    assert "scripts/check_release_version.py" in workflow
    assert "scripts/check_launchers.py" in workflow
    assert "gh release create" in workflow
    assert "dist/*.zip" in workflow
    assert "dist/SHA256SUMS.txt" in workflow
    assert "secrets." not in workflow


def test_release_version_check_accepts_manifest_version_and_rejects_mismatch() -> None:
    checker = PROJECT_ROOT / "scripts/check_release_version.py"

    accepted = subprocess.run(
        [sys.executable, str(checker), "v0.2.0"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    rejected = subprocess.run(
        [sys.executable, str(checker), "v9.9.9"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert accepted.returncode == 0, accepted.stderr
    assert rejected.returncode != 0
    assert "manifest version 0.2.0" in rejected.stderr
