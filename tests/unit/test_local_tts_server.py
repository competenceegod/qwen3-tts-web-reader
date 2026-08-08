import json
import struct
import threading
import wave
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from booksite.site.local_server import (
    BooksiteServer,
    MlxTtsEngine,
    RequestError,
    TorchTtsEngine,
    TtsEngine,
    TtsSessionStore,
    audio_to_pcm16_bytes,
    audio_to_wav_bytes,
    create_tts_engine,
    discover_model_snapshot,
    generation_token_limit,
    is_loopback_client,
    make_handler,
    parse_tts_request,
    start_background_warm_up,
    wav_stream_header,
)


def _model_snapshot(root: Path, name: str = "snapshot-a") -> Path:
    snapshot = (
        root
        / ".cache/huggingface/hub"
        / "models--mlx-community--Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16"
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


def test_discover_model_snapshot_uses_the_independent_huggingface_cache(
    tmp_path: Path,
) -> None:
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
        environ={"BOOKSITE_TTS_MLX_MODEL": str(explicit)},
    )

    assert result == explicit
    assert result != cached


def test_discover_model_snapshot_ignores_incomplete_model(tmp_path: Path) -> None:
    snapshot = _model_snapshot(tmp_path)
    (snapshot / "speech_tokenizer/model.safetensors").unlink()

    assert discover_model_snapshot(home=tmp_path, environ={}) is None


@pytest.mark.parametrize(
    ("platform_name", "expected_type"),
    [("darwin", MlxTtsEngine), ("win32", TorchTtsEngine), ("linux", TorchTtsEngine)],
)
def test_auto_backend_selects_the_platform_runtime(
    platform_name: str,
    expected_type: type[object],
) -> None:
    engine = create_tts_engine(
        backend="auto",
        platform_name=platform_name,
        environ={},
    )

    assert isinstance(engine, expected_type)


def test_backend_environment_override_wins_over_auto_selection() -> None:
    engine = create_tts_engine(
        backend="auto",
        platform_name="darwin",
        environ={"BOOKSITE_TTS_BACKEND": "torch"},
    )

    assert isinstance(engine, TorchTtsEngine)


class _FakeTorchModel:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate_custom_voice(self, **options: object):
        self.calls.append(options)
        return [[-0.5, 0.0, 0.5]], 24_000


def test_torch_engine_uses_official_custom_voice_contract() -> None:
    engine = TorchTtsEngine(
        environ={
            "BOOKSITE_TTS_TORCH_MODEL": "Qwen/test-model",
            "BOOKSITE_TTS_SPEAKER": "Ryan",
        }
    )
    model = _FakeTorchModel()
    engine._model = model

    chunks = list(engine.stream_pcm("Read this sentence."))

    assert chunks == [audio_to_pcm16_bytes([-0.5, 0.0, 0.5])]
    assert engine.sample_rate == 24_000
    assert model.calls == [
        {
            "text": "Read this sentence.",
            "language": "Auto",
            "speaker": "Ryan",
            "non_streaming_mode": True,
            "max_new_tokens": generation_token_limit("Read this sentence."),
        }
    ]


class _FakeMlxCustomVoiceModel:
    sample_rate = 24_000

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate_custom_voice(self, **options: object):
        self.calls.append(options)
        yield _AudioResult([0.25, -0.25])


def test_mlx_engine_downloads_its_own_custom_voice_model() -> None:
    engine = MlxTtsEngine(environ={})
    model = _FakeMlxCustomVoiceModel()
    engine._model = model

    chunks = list(engine.stream_pcm("Read independently."))

    assert "PDFgear" not in engine.model_id
    assert engine.model_id == "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16"
    assert chunks == [audio_to_pcm16_bytes([0.25, -0.25])]
    assert model.calls == [
        {
            "text": "Read independently.",
            "speaker": "Ryan",
            "language": "Auto",
            "max_tokens": generation_token_limit("Read independently."),
            "verbose": False,
            "stream": True,
            "streaming_interval": 0.5,
        }
    ]


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


def test_streaming_wav_header_allows_unknown_audio_length() -> None:
    header = wav_stream_header(sample_rate=24_000)

    assert len(header) == 44
    assert header[:4] == b"RIFF"
    assert header[8:12] == b"WAVE"
    assert struct.unpack_from("<I", header, 4)[0] == 0xFFFFFFFF
    assert struct.unpack_from("<I", header, 24)[0] == 24_000
    assert struct.unpack_from("<I", header, 40)[0] == 0xFFFFFFFF


def test_audio_to_pcm16_bytes_clips_samples_without_wav_header() -> None:
    pcm = audio_to_pcm16_bytes([-1.5, -0.25, 0.25, 1.5])

    assert len(pcm) == 8
    assert struct.unpack("<hhhh", pcm) == (-32767, -8192, 8192, 32767)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("short", 42),
        ("中" * 100, 800),
        ("x" * 2_000, 4_096),
        (
            "Without parallel execution, you must accept slow sequential processing, "
            "implement complex threading or async logic manually, risk inconsistent "
            "state management across threads, and handle thread safety and "
            "synchronization issues.",
            322,
        ),
    ],
)
def test_generation_token_limit_matches_spoken_content(text: str, expected: int) -> None:
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


class _FakeResult:
    audio = [-0.5, 0.0, 0.5]
    sample_rate = 24_000


class _FakeModel:
    sample_rate = 24_000

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(self, text: str, **options: object):
        self.calls.append({"text": text, **options})
        yield _FakeResult()


def test_tts_engine_requests_small_streaming_chunks() -> None:
    engine = TtsEngine()
    model = _FakeModel()
    engine._model = model
    engine.reference_audio = None

    chunks = list(engine.stream_pcm("Read this sentence."))

    assert len(chunks) == 1
    assert chunks[0] == audio_to_pcm16_bytes(_FakeResult.audio)
    assert model.calls[0]["stream"] is True
    assert model.calls[0]["streaming_interval"] == 0.5


class _AudioResult:
    sample_rate = 24_000

    def __init__(self, audio: list[float]) -> None:
        self.audio = audio


class _QuietThenSpeechModel:
    sample_rate = 24_000

    def __init__(self) -> None:
        self.texts: list[str] = []

    def generate(self, text: str, **options: object):
        del options
        self.texts.append(text)
        if "," in text:
            yield _AudioResult([0.002] * 12_000)
            yield _AudioResult([0.002] * 12_000)
            return
        yield _AudioResult([0.25, -0.25] * 6_000)


def test_tts_engine_discards_quiet_failure_and_retries_without_commas() -> None:
    engine = TtsEngine()
    model = _QuietThenSpeechModel()
    engine._model = model
    engine.reference_audio = None

    chunks = list(
        engine.stream_pcm(
            "In this chapter, we will discuss the following important topics:"
        )
    )

    assert model.texts == [
        "In this chapter, we will discuss the following important topics:",
        "In this chapter we will discuss the following important topics:",
    ]
    assert chunks == [audio_to_pcm16_bytes([0.25, -0.25] * 6_000)]


def test_tts_engine_warms_model_with_a_short_stream() -> None:
    engine = TtsEngine()
    model = _FakeModel()
    engine._model = model
    engine.reference_audio = None

    assert engine.warm_up()

    assert model.calls[0]["text"] == "Ready."
    assert model.calls[0]["stream"] is True


def test_background_warm_up_keeps_status_endpoint_reachable() -> None:
    warm_up_started = threading.Event()
    release_warm_up = threading.Event()

    class BlockingWarmUpEngine:
        sample_rate = 24_000

        def status(self) -> dict[str, object]:
            return {
                "available": True,
                "model": "fake",
                "runtime": True,
                "warming": not release_warm_up.is_set(),
            }

        def warm_up(self) -> bool:
            warm_up_started.set()
            release_warm_up.wait(timeout=3)
            return True

    engine = BlockingWarmUpEngine()
    server = BooksiteServer(("127.0.0.1", 0), make_handler(None, engine))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    warm_thread = start_background_warm_up(engine)
    try:
        assert warm_up_started.wait(timeout=1)
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/tts/status",
            timeout=1,
        ) as response:
            assert json.load(response)["warming"] is True
    finally:
        release_warm_up.set()
        warm_thread.join(timeout=1)
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1)


def test_tts_session_is_one_time_and_expires() -> None:
    now = [10.0]
    sessions = TtsSessionStore(ttl_seconds=30, clock=lambda: now[0])
    token = sessions.create("Read once.")

    assert sessions.consume(token) == "Read once."
    with pytest.raises(RequestError) as reused:
        sessions.consume(token)
    assert reused.value.status == 404

    expired = sessions.create("Too late.")
    now[0] = 41.0
    with pytest.raises(RequestError) as expiry:
        sessions.consume(expired)
    assert expiry.value.status == 404


class _FakeStreamingEngine:
    sample_rate = 24_000

    def __init__(self) -> None:
        self.texts: list[str] = []

    def status(self) -> dict[str, object]:
        return {"available": True, "model": "fake", "runtime": True}

    def require_available(self) -> None:
        return

    def stream_pcm(self, text: str):
        self.texts.append(text)
        yield audio_to_pcm16_bytes([0.0, 0.25])
        yield audio_to_pcm16_bytes([-0.25, 0.0])


def test_http_api_returns_one_time_streaming_wav_url(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<title>Book</title>", encoding="utf-8")
    engine = _FakeStreamingEngine()
    server = BooksiteServer(("127.0.0.1", 0), make_handler(tmp_path, engine))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    request = Request(
        f"{base_url}/api/tts",
        data=json.dumps({"text": "Stream this."}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=3) as response:
            assert response.status == 201
            stream_url = json.load(response)["streamUrl"]
        with urlopen(f"{base_url}{stream_url}", timeout=3) as response:
            audio = response.read()
            assert response.headers["Content-Type"] == "audio/wav"
        assert audio.startswith(b"RIFF")
        assert audio[44:] == (
            audio_to_pcm16_bytes([0.0, 0.25])
            + audio_to_pcm16_bytes([-0.25, 0.0])
        )
        assert engine.texts == ["Stream this."]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
