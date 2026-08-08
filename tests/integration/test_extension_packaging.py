import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGER = PROJECT_ROOT / "scripts/package_extension.py"
VERSION = "0.2.0"
PLATFORMS = ("macos", "windows", "linux")


def _package(output_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PACKAGER), "--output-dir", str(output_dir)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_packager_builds_reproducible_platform_archives(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_result = _package(first)
    second_result = _package(second)

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    expected_names = {
        f"qwen3-tts-web-reader-{VERSION}-{platform}.zip" for platform in PLATFORMS
    }
    assert {path.name for path in first.glob("*.zip")} == expected_names
    assert {path.name: _digest(path) for path in first.glob("*.zip")} == {
        path.name: _digest(path) for path in second.glob("*.zip")
    }
    assert (first / "SHA256SUMS.txt").read_text(encoding="utf-8").count(".zip") == 3


def test_platform_archives_are_safe_and_self_contained(tmp_path: Path) -> None:
    result = _package(tmp_path)
    assert result.returncode == 0, result.stderr

    for platform in PLATFORMS:
        archive = tmp_path / f"qwen3-tts-web-reader-{VERSION}-{platform}.zip"
        root = f"qwen3-tts-web-reader-{VERSION}-{platform}"
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            assert names
            assert all(PurePosixPath(name).parts[0] == root for name in names)
            assert all(not PurePosixPath(name).is_absolute() for name in names)
            assert all(".." not in PurePosixPath(name).parts for name in names)
            assert f"{root}/extension/manifest.json" in names
            assert f"{root}/service/local_server.py" in names
            assert f"{root}/README.md" in names
            assert f"{root}/LICENSE" in names
            manifest = json.loads(
                package.read(f"{root}/extension/manifest.json").decode("utf-8")
            )
            assert manifest["version"] == VERSION

            launchers = {
                "macos": ["start-qwen-reader.command"],
                "windows": ["start-qwen-reader.cmd", "start-qwen-reader.ps1"],
                "linux": ["start-qwen-reader.sh"],
            }[platform]
            for launcher in launchers:
                assert f"{root}/{launcher}" in names

            forbidden_suffixes = (".pdf", ".wav", ".env", ".safetensors")
            assert not any(name.casefold().endswith(forbidden_suffixes) for name in names)
            payload = b"\n".join(package.read(name) for name in names if not name.endswith("/"))
            assert b"/Users/" not in payload
            assert b"C:\\Users\\" not in payload


def test_platform_launchers_select_the_expected_backend(tmp_path: Path) -> None:
    result = _package(tmp_path)
    assert result.returncode == 0, result.stderr

    expected = {
        "macos": ("start-qwen-reader.command", "--tts-backend mlx", "mlx-audio==0.4.6"),
        "windows": ("start-qwen-reader.ps1", "--tts-backend torch", "qwen-tts==0.1.1"),
        "linux": ("start-qwen-reader.sh", "--tts-backend torch", "qwen-tts==0.1.1"),
    }
    for platform, (launcher, backend, runtime) in expected.items():
        archive = tmp_path / f"qwen3-tts-web-reader-{VERSION}-{platform}.zip"
        root = f"qwen3-tts-web-reader-{VERSION}-{platform}"
        with zipfile.ZipFile(archive) as package:
            script = package.read(f"{root}/{launcher}").decode("utf-8")
        assert "127.0.0.1" in script
        assert "--port 8765" in script
        assert backend in script
        assert runtime in script
