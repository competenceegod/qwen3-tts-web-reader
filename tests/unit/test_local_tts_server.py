import json
import wave
from io import BytesIO
from pathlib import Path

import pytest

from booksite.site.local_server import (
    RequestError,
    TtsEngine,
    audio_to_wav_bytes,
    discover_model_snapshot,
    generation_token_limit,
    is_loopback_client,
    parse_tts_request,
)


def _model_snapshot(root: Path, name: str = "snapshot-a") -> Path:
    snapshot = (
        root
        / "Library/Containers/com.pdfeditor.pdfeditormac/Data/Library/Application Support"
        / "huggingface/hub"
        / "models--mlx-community--Qwen3-TTS-12Hz-0.6B-Base-8bit"
        / "snapshots"
        / name
    )
    (snapshot / "speech_tokenizer").mkdir(parents=True)
    for relative_path in (
        "config.json",
        "model.safetensors",
        "speech_tokenizer/config.json",
        "speech_tokenizer/model.safetensors",
    ):
        (snapshot / relative_path).write_bytes(b"test")
    return snapshot


def test_discover_model_snapshot_reuses_pdfgear_cache(tmp_path: Path) -> None:
    older = _model_snapshot(tmp_path, "older")
    newer = _model_snapshot(tmp_path, "newer")
    older.touch()
    newer.touch()

    assert discover_model_snapshot(home=tmp_path, environ={}) == newer


def test_discover_model_snapshot_prefers_explicit_environment_path(tmp_path: Path) -> None:
    cached = _model_snapshot(tmp_path, "cached")
    explicit = _model_snapshot(tmp_path / "explicit-home", "chosen")

    result = discover_model_snapshot(
        home=tmp_path,
        environ={"BOOKSITE_TTS_MODEL": str(explicit)},
    )

    assert result == explicit
    assert result != cached


def test_discover_model_snapshot_ignores_incomplete_model(tmp_path: Path) -> None:
    snapshot = _model_snapshot(tmp_path)
    (snapshot / "speech_tokenizer/model.safetensors").unlink()

    assert discover_model_snapshot(home=tmp_path, environ={}) is None


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "::ffff:127.0.0.1"])
def test_loopback_clients_are_allowed(host: str) -> None:
    assert is_loopback_client(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.8", "10.0.0.4", "example.com"])
def test_non_loopback_clients_are_rejected(host: str) -> None:
    assert not is_loopback_client(host)


def test_parse_tts_request_normalizes_selected_text() -> None:
    body = json.dumps({"text": "  First line.\n\n Second line.  "}).encode()

    assert parse_tts_request(body, "application/json; charset=utf-8") == (
        "First line.\nSecond line."
    )


@pytest.mark.parametrize(
    ("body", "content_type", "status"),
    [
        (b"{}", "text/plain", 415),
        (b"{", "application/json", 400),
        (b'{"text": ""}', "application/json", 400),
        (json.dumps({"text": "x" * 2001}).encode(), "application/json", 413),
    ],
)
def test_parse_tts_request_rejects_unsafe_payloads(
    body: bytes,
    content_type: str,
    status: int,
) -> None:
    with pytest.raises(RequestError) as error:
        parse_tts_request(body, content_type)

    assert error.value.status == status


def test_audio_to_wav_bytes_writes_mono_24khz_pcm() -> None:
    wav_bytes = audio_to_wav_bytes([-1.5, -0.25, 0.25, 1.5], sample_rate=24_000)

    with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 24_000
        assert wav_file.getnframes() == 4


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("short", 256),
        ("中" * 100, 800),
        ("x" * 2_000, 4_096),
    ],
)
def test_generation_token_limit_bounds_runaway_audio(text: str, expected: int) -> None:
    assert generation_token_limit(text) == expected


def test_tts_engine_rejects_concurrent_generation() -> None:
    engine = TtsEngine()
    engine._lock.acquire()
    try:
        with pytest.raises(RequestError) as error:
            engine.synthesize("second request")
    finally:
        engine._lock.release()

    assert error.value.status == 409
