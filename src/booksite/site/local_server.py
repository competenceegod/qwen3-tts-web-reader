#!/usr/bin/env python3
"""Serve a generated Docusaurus build and optional local Qwen3-TTS API."""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import math
import os
import struct
import sys
import threading
import wave
import webbrowser
from collections.abc import Iterable, Mapping, Sequence
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

MAX_REQUEST_BYTES = 16_384
MAX_TEXT_CHARACTERS = 2_000
MODEL_CACHE_NAME = "models--mlx-community--Qwen3-TTS-12Hz-0.6B-Base-8bit"
REQUIRED_MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "speech_tokenizer/config.json",
    "speech_tokenizer/model.safetensors",
)


class RequestError(ValueError):
    """A client-visible request error with an HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _is_complete_model(path: Path) -> bool:
    return path.is_dir() and all((path / relative).is_file() for relative in REQUIRED_MODEL_FILES)


def discover_model_snapshot(
    *,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    """Find an existing compatible model without downloading another copy."""

    environment = os.environ if environ is None else environ
    explicit = environment.get("BOOKSITE_TTS_MODEL")
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if _is_complete_model(candidate) else None

    user_home = Path.home() if home is None else home
    snapshots_dir = (
        user_home
        / "Library/Containers/com.pdfeditor.pdfeditormac/Data/Library/Application Support"
        / "huggingface/hub"
        / MODEL_CACHE_NAME
        / "snapshots"
    )
    if not snapshots_dir.is_dir():
        return None
    candidates = [
        candidate for candidate in snapshots_dir.iterdir() if _is_complete_model(candidate)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: (candidate.stat().st_mtime_ns, candidate.name))


def discover_reference_audio() -> Path | None:
    """Return PDFgear's local reference voice sample when it is installed."""

    configured = os.environ.get("BOOKSITE_TTS_REFERENCE_AUDIO")
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path("/Applications/PDFgear.app/Contents/Resources/refAudio.wav"),
    ]
    return next(
        (candidate.resolve() for candidate in candidates if candidate and candidate.is_file()),
        None,
    )


def is_loopback_client(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_tts_request(body: bytes, content_type: str) -> str:
    if content_type.partition(";")[0].strip().casefold() != "application/json":
        raise RequestError(415, "仅接受 application/json 请求。")
    if len(body) > MAX_REQUEST_BYTES:
        raise RequestError(413, "请求内容过大。")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RequestError(400, "JSON 格式无效。") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise RequestError(400, "缺少文字内容。")
    text = "\n".join(line.strip() for line in payload["text"].splitlines() if line.strip())
    if not text:
        raise RequestError(400, "请先选择要朗读的文字。")
    if len(text) > MAX_TEXT_CHARACTERS:
        raise RequestError(413, f"一次最多朗读 {MAX_TEXT_CHARACTERS} 个字符。")
    return text


def generation_token_limit(text: str) -> int:
    """Bound audio generation while leaving room for slower-spoken CJK text."""

    return min(4_096, max(256, len(text) * 8))


def _finite_pcm_sample(value: float) -> int:
    normalized = float(value)
    if not math.isfinite(normalized):
        normalized = 0.0
    return round(max(-1.0, min(1.0, normalized)) * 32767)


def audio_to_wav_bytes(audio: Iterable[float], *, sample_rate: int) -> bytes:
    pcm = bytearray()
    for value in audio:
        pcm.extend(struct.pack("<h", _finite_pcm_sample(value)))
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


def _flatten_audio(values: object) -> Iterable[float]:
    if hasattr(values, "tolist"):
        values = values.tolist()
    if isinstance(values, Sequence):
        for value in values:
            if isinstance(value, Sequence):
                yield from _flatten_audio(value)
            else:
                yield float(value)
        return
    raise RuntimeError("语音模型返回了无法识别的音频格式。")


class TtsEngine:
    """Lazy, serialized wrapper around MLX-Audio."""

    def __init__(self) -> None:
        self.model_path = discover_model_snapshot()
        self.reference_audio = discover_reference_audio()
        self._model: object | None = None
        self._lock = threading.Lock()

    @property
    def runtime_available(self) -> bool:
        return importlib.util.find_spec("mlx_audio") is not None

    def status(self) -> dict[str, object]:
        runtime = self.runtime_available
        model = self.model_path is not None
        return {
            "available": runtime and model,
            "model": self.model_path.name if self.model_path else None,
            "runtime": runtime,
            "referenceVoice": self.reference_audio is not None,
        }

    def _load_model(self) -> object:
        if self._model is None:
            if self.model_path is None:
                raise RequestError(503, "未找到 PDFgear 下载的兼容 Qwen3-TTS 模型。")
            if not self.runtime_available:
                raise RequestError(503, "未安装 MLX 语音运行库，请使用“打开网站.command”启动。")
            from mlx_audio.tts.utils import load_model

            self._model = load_model(str(self.model_path))
        return self._model

    def synthesize(self, text: str) -> bytes:
        if not self._lock.acquire(blocking=False):
            raise RequestError(409, "正在生成上一段语音，请稍后再试。")
        try:
            model = self._load_model()
            options: dict[str, object] = {
                "lang_code": "auto",
                "max_tokens": generation_token_limit(text),
                "verbose": False,
            }
            if self.reference_audio:
                options["ref_audio"] = str(self.reference_audio)
            samples: list[float] = []
            sample_rate = int(getattr(model, "sample_rate", 24_000))
            for result in model.generate(text, **options):
                samples.extend(_flatten_audio(result.audio))
                sample_rate = int(getattr(result, "sample_rate", sample_rate))
            if not samples:
                raise RuntimeError("语音模型没有返回音频。")
            return audio_to_wav_bytes(samples, sample_rate=sample_rate)
        finally:
            self._lock.release()


class BooksiteServer(ThreadingHTTPServer):
    daemon_threads = True


def make_handler(build_dir: Path, engine: TtsEngine) -> type[SimpleHTTPRequestHandler]:
    class BooksiteRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(build_dir), **kwargs)

        def _require_loopback(self) -> None:
            if not is_loopback_client(self.client_address[0]):
                raise RequestError(403, "本地语音服务只接受本机请求。")

        def _send_json(self, status: int, payload: Mapping[str, object]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.partition("?")[0] != "/api/tts/status":
                super().do_GET()
                return
            try:
                self._require_loopback()
                self._send_json(200, engine.status())
            except RequestError as error:
                self._send_json(error.status, {"error": str(error)})

        def do_POST(self) -> None:
            if self.path.partition("?")[0] != "/api/tts":
                self._send_json(404, {"error": "接口不存在。"})
                return
            try:
                self._require_loopback()
                try:
                    content_length = int(self.headers.get("Content-Length", ""))
                except ValueError as error:
                    raise RequestError(400, "Content-Length 无效。") from error
                if content_length < 0:
                    raise RequestError(400, "Content-Length 无效。")
                if content_length > MAX_REQUEST_BYTES:
                    raise RequestError(413, "请求内容过大。")
                body = self.rfile.read(content_length)
                text = parse_tts_request(body, self.headers.get("Content-Type", ""))
                wav_bytes = engine.synthesize(text)
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(wav_bytes)
            except RequestError as error:
                self._send_json(error.status, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:
                print(f"Qwen3-TTS error: {error}", file=sys.stderr, flush=True)
                self._send_json(500, {"error": "本地语音生成失败，请查看启动窗口中的错误。"})

    return BooksiteRequestHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview the generated book site.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--no-open", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not is_loopback_client(args.host):
        raise SystemExit("为保护本地语音接口，--host 必须是 127.0.0.1 或 ::1。")
    build_dir = Path(__file__).resolve().parent / "build"
    if not (build_dir / "index.html").is_file():
        raise SystemExit(
            "未找到 build/index.html。请先运行 PDF 转换，或在本书目录执行 pnpm build。"
        )

    engine = TtsEngine()
    handler = make_handler(build_dir, engine)
    try:
        server = BooksiteServer((args.host, args.port), handler)
    except OSError as error:
        raise SystemExit(
            f"无法启动本地网站：{error}。可尝试 python3 serve-local.py --port 8001"
        ) from error

    url = f"http://{args.host}:{server.server_port}/"
    print(f"本地网站：{url}", flush=True)
    print("保持此窗口开启；按 Control-C 停止。", flush=True)
    if not args.no_open:
        opener = threading.Timer(0.2, webbrowser.open, args=(url,))
        opener.daemon = True
        opener.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n本地网站已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
