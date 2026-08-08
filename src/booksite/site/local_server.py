#!/usr/bin/env python3
"""Serve a generated Docusaurus build and optional local Qwen3-TTS API."""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import math
import os
import re
import secrets
import struct
import sys
import threading
import time
import wave
import webbrowser
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

MAX_REQUEST_BYTES = 16_384
MAX_TEXT_CHARACTERS = 2_000
DEFAULT_MLX_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16"
DEFAULT_TORCH_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
DEFAULT_SPEAKER = "Ryan"
MODEL_CACHE_NAME = "models--mlx-community--Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16"
REQUIRED_MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "speech_tokenizer/config.json",
    "speech_tokenizer/model.safetensors",
)
STREAMING_INTERVAL_SECONDS = 0.5
STREAM_SESSION_TTL_SECONDS = 60
MAX_STREAM_SESSIONS = 8
LOW_ENERGY_FAILURE_SECONDS = 1.0
LOW_ENERGY_RMS_THRESHOLD = 0.01
LATIN_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")
CJK_CHARACTER_PATTERN = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]"
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
    explicit = environment.get("BOOKSITE_TTS_MLX_MODEL")
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if _is_complete_model(candidate) else None

    user_home = Path.home() if home is None else home
    snapshots_dir = user_home / ".cache/huggingface/hub" / MODEL_CACHE_NAME / "snapshots"
    if not snapshots_dir.is_dir():
        return None
    candidates = [
        candidate for candidate in snapshots_dir.iterdir() if _is_complete_model(candidate)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: (candidate.stat().st_mtime_ns, candidate.name))


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
    """Bound audio generation using units that approximate spoken duration."""

    latin_words = LATIN_WORD_PATTERN.findall(text)
    cjk_characters = len(CJK_CHARACTER_PATTERN.findall(text))
    longest_latin_word = max(map(len, latin_words), default=0)
    if cjk_characters:
        estimate = cjk_characters * 8 + len(latin_words) * 10
    elif longest_latin_word > 32:
        # Preserve a conservative budget for identifiers or unbroken synthetic input.
        estimate = len(text) * 8
    else:
        estimate = 32 + len(latin_words) * 10
    return min(4_096, max(32, estimate))


def _finite_pcm_sample(value: float) -> int:
    normalized = float(value)
    if not math.isfinite(normalized):
        normalized = 0.0
    return round(max(-1.0, min(1.0, normalized)) * 32767)


def audio_to_pcm16_bytes(audio: Iterable[float]) -> bytes:
    pcm = bytearray()
    for value in audio:
        pcm.extend(struct.pack("<h", _finite_pcm_sample(value)))
    return bytes(pcm)


def audio_to_wav_bytes(audio: Iterable[float], *, sample_rate: int) -> bytes:
    pcm = audio_to_pcm16_bytes(audio)
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


def wav_stream_header(*, sample_rate: int) -> bytes:
    """Return a PCM WAV header whose data length is intentionally unknown."""

    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        0xFFFFFFFF,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        sample_rate * 2,
        2,
        16,
        b"data",
        0xFFFFFFFF,
    )


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


def _audio_rms(samples: Sequence[float]) -> float:
    if not samples:
        return 0.0
    square_sum = 0.0
    for value in samples:
        sample = float(value)
        if math.isfinite(sample):
            square_sum += sample * sample
    return math.sqrt(square_sum / len(samples))


def _spoken_text_candidates(text: str) -> tuple[str, ...]:
    simplified = re.sub(r",\s*", " ", text)
    simplified = re.sub(r"\s+", " ", simplified).strip()
    return (text,) if simplified == text else (text, simplified)


class TtsSessionStore:
    """Small one-time store that keeps selected text out of stream URLs."""

    def __init__(
        self,
        *,
        ttl_seconds: float = STREAM_SESSION_TTL_SECONDS,
        max_sessions: int = MAX_STREAM_SESSIONS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._clock = clock
        self._sessions: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def _discard_expired(self, now: float) -> None:
        expired = [
            token
            for token, (created_at, _) in self._sessions.items()
            if now - created_at > self.ttl_seconds
        ]
        for token in expired:
            self._sessions.pop(token, None)

    def create(self, text: str) -> str:
        with self._lock:
            now = self._clock()
            self._discard_expired(now)
            while len(self._sessions) >= self.max_sessions:
                oldest = min(self._sessions, key=lambda token: self._sessions[token][0])
                self._sessions.pop(oldest)
            token = secrets.token_urlsafe(24)
            self._sessions[token] = (now, text)
            return token

    def consume(self, token: str) -> str:
        with self._lock:
            self._discard_expired(self._clock())
            session = self._sessions.pop(token, None)
        if session is None:
            raise RequestError(404, "朗读链接已失效，请重新选择文字。")
        return session[1]


class MlxTtsEngine:
    """Lazy, serialized Qwen3-TTS wrapper optimized for Apple Silicon."""

    def __init__(self, *, environ: Mapping[str, str] | None = None) -> None:
        environment = os.environ if environ is None else environ
        configured_model = environment.get("BOOKSITE_TTS_MLX_MODEL")
        cached_model = discover_model_snapshot(environ=environment)
        self.model_id = configured_model or str(cached_model or DEFAULT_MLX_MODEL)
        self.model_path = cached_model
        self.speaker = environment.get("BOOKSITE_TTS_SPEAKER", DEFAULT_SPEAKER)
        self._model: object | None = None
        self._lock = threading.Lock()
        self._warming = False
        self._state_lock = threading.Lock()

    @property
    def runtime_available(self) -> bool:
        return self._model is not None or importlib.util.find_spec("mlx_audio") is not None

    @property
    def sample_rate(self) -> int:
        return int(getattr(self._model, "sample_rate", 24_000))

    def status(self) -> dict[str, object]:
        runtime = self.runtime_available
        with self._state_lock:
            warming = self._warming
        return {
            "available": runtime,
            "backend": "mlx",
            "model": self.model_id,
            "runtime": runtime,
            "speaker": self.speaker,
            "downloadRequired": self.model_path is None,
            "warming": warming,
        }

    def require_available(self) -> None:
        if not self.runtime_available:
            raise RequestError(503, "未安装 MLX 语音运行库，请使用平台启动器启动。")

    def _load_model(self) -> object:
        if self._model is None:
            self.require_available()
            from mlx_audio.tts.utils import load_model

            self._model = load_model(self.model_id)
        return self._model

    def _generation_options(self, text: str, *, max_tokens: int | None = None) -> dict[str, object]:
        options: dict[str, object] = {
            "lang_code": "auto",
            "max_tokens": max_tokens or generation_token_limit(text),
            "verbose": False,
            "stream": True,
            "streaming_interval": STREAMING_INTERVAL_SECONDS,
        }
        return options

    def _generate(self, model: object, text: str, *, max_tokens: int | None = None) -> object:
        options = self._generation_options(text, max_tokens=max_tokens)
        custom_voice = getattr(model, "generate_custom_voice", None)
        if custom_voice is not None:
            options.update({"speaker": self.speaker, "language": "Auto"})
            options.pop("lang_code", None)
            return custom_voice(text=text, **options)
        return model.generate(text, **options)

    def stream_pcm(self, text: str) -> Iterator[bytes]:
        if not self._lock.acquire(blocking=False):
            raise RequestError(409, "正在生成上一段语音，请稍后再试。")
        try:
            model = self._load_model()
            for candidate in _spoken_text_candidates(text):
                emitted = False
                quiet_chunks: list[bytes] = []
                quiet_seconds = 0.0
                generation = self._generate(model, candidate)
                try:
                    for result in generation:
                        samples = list(_flatten_audio(result.audio))
                        if _audio_rms(samples) < LOW_ENERGY_RMS_THRESHOLD:
                            quiet_chunks.append(audio_to_pcm16_bytes(samples))
                            quiet_seconds += len(samples) / self.sample_rate
                            if quiet_seconds >= LOW_ENERGY_FAILURE_SECONDS:
                                break
                            continue
                        for chunk in quiet_chunks:
                            emitted = True
                            yield chunk
                        quiet_chunks.clear()
                        quiet_seconds = 0.0
                        emitted = True
                        yield audio_to_pcm16_bytes(samples)
                finally:
                    close_generation = getattr(generation, "close", None)
                    if close_generation is not None:
                        close_generation()
                if emitted:
                    return
            raise RuntimeError("语音模型没有返回有效语音。")
        finally:
            self._lock.release()

    def synthesize(self, text: str) -> bytes:
        pcm = b"".join(self.stream_pcm(text))
        output = BytesIO()
        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm)
        return output.getvalue()

    def warm_up(self) -> bool:
        if not self.runtime_available:
            return False
        with self._state_lock:
            self._warming = True
        if not self._lock.acquire(blocking=False):
            with self._state_lock:
                self._warming = False
            return False
        try:
            model = self._load_model()
            for _ in self._generate(model, "Ready.", max_tokens=64):
                pass
            return True
        except Exception as error:
            print(f"Qwen3-TTS warm-up error: {error}", file=sys.stderr, flush=True)
            return False
        finally:
            self._lock.release()
            with self._state_lock:
                self._warming = False


TtsEngine = MlxTtsEngine


class TorchTtsEngine:
    """Cross-platform wrapper around Qwen's official PyTorch package."""

    def __init__(self, *, environ: Mapping[str, str] | None = None) -> None:
        environment = os.environ if environ is None else environ
        self.model_id = environment.get("BOOKSITE_TTS_TORCH_MODEL", DEFAULT_TORCH_MODEL)
        self.speaker = environment.get("BOOKSITE_TTS_SPEAKER", DEFAULT_SPEAKER)
        self.requested_device = environment.get("BOOKSITE_TTS_DEVICE", "auto")
        self._model: object | None = None
        self._sample_rate = 24_000
        self._lock = threading.Lock()
        self._warming = False
        self._state_lock = threading.Lock()
        self._device = "unresolved"

    @property
    def runtime_available(self) -> bool:
        return self._model is not None or (
            importlib.util.find_spec("qwen_tts") is not None
            and importlib.util.find_spec("torch") is not None
        )

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def status(self) -> dict[str, object]:
        with self._state_lock:
            warming = self._warming
        return {
            "available": self.runtime_available,
            "backend": "torch",
            "model": self.model_id,
            "runtime": self.runtime_available,
            "speaker": self.speaker,
            "device": self._device,
            "warming": warming,
        }

    def require_available(self) -> None:
        if not self.runtime_available:
            raise RequestError(503, "未安装官方 qwen-tts 运行库，请使用平台启动器启动。")

    def _runtime_options(self) -> dict[str, object]:
        import torch

        requested = self.requested_device.casefold()
        if requested == "auto":
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif requested == "cuda":
            device = "cuda:0"
        elif requested == "cpu" or requested.startswith("cuda:"):
            device = requested
        else:
            raise RequestError(503, "BOOKSITE_TTS_DEVICE 仅支持 auto、cpu、cuda 或 cuda:N。")
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise RequestError(503, "已要求使用 CUDA，但当前 PyTorch 无法访问 NVIDIA GPU。")
        dtype = torch.float32
        if device.startswith("cuda"):
            dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        self._device = device
        return {"device_map": device, "dtype": dtype, "attn_implementation": "sdpa"}

    def _load_model(self) -> object:
        if self._model is None:
            self.require_available()
            from qwen_tts import Qwen3TTSModel

            self._model = Qwen3TTSModel.from_pretrained(
                self.model_id,
                **self._runtime_options(),
            )
        return self._model

    def _generate(self, model: object, text: str) -> tuple[list[object], int]:
        return model.generate_custom_voice(
            text=text,
            language="Auto",
            speaker=self.speaker,
            non_streaming_mode=True,
            max_new_tokens=generation_token_limit(text),
        )

    def stream_pcm(self, text: str) -> Iterator[bytes]:
        if not self._lock.acquire(blocking=False):
            raise RequestError(409, "正在生成上一段语音，请稍后再试。")
        try:
            model = self._load_model()
            for candidate in _spoken_text_candidates(text):
                wavs, sample_rate = self._generate(model, candidate)
                if not wavs:
                    continue
                samples = list(_flatten_audio(wavs[0]))
                if _audio_rms(samples) < LOW_ENERGY_RMS_THRESHOLD:
                    continue
                self._sample_rate = int(sample_rate)
                yield audio_to_pcm16_bytes(samples)
                return
            raise RuntimeError("语音模型没有返回有效语音。")
        finally:
            self._lock.release()

    def synthesize(self, text: str) -> bytes:
        pcm = b"".join(self.stream_pcm(text))
        output = BytesIO()
        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm)
        return output.getvalue()

    def warm_up(self) -> bool:
        if not self.runtime_available:
            return False
        with self._state_lock:
            self._warming = True
        try:
            for _ in self.stream_pcm("Ready."):
                pass
            return True
        except Exception as error:
            print(f"Qwen3-TTS warm-up error: {error}", file=sys.stderr, flush=True)
            return False
        finally:
            with self._state_lock:
                self._warming = False


def create_tts_engine(
    *,
    backend: str = "auto",
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> MlxTtsEngine | TorchTtsEngine:
    environment = os.environ if environ is None else environ
    selected = environment.get("BOOKSITE_TTS_BACKEND", backend).casefold()
    current_platform = sys.platform if platform_name is None else platform_name
    if selected == "auto":
        selected = "mlx" if current_platform == "darwin" else "torch"
    if selected == "mlx":
        return MlxTtsEngine(environ=environment)
    if selected == "torch":
        return TorchTtsEngine(environ=environment)
    raise ValueError("tts backend must be auto, mlx, or torch")


def start_background_warm_up(engine: MlxTtsEngine | TorchTtsEngine) -> threading.Thread:
    """Warm the model without delaying the loopback HTTP listener."""

    thread = threading.Thread(
        target=engine.warm_up,
        name="booksite-tts-warm-up",
        daemon=True,
    )
    thread.start()
    return thread


class BooksiteServer(ThreadingHTTPServer):
    daemon_threads = True


def make_handler(
    build_dir: Path | None,
    engine: MlxTtsEngine | TorchTtsEngine,
    sessions: TtsSessionStore | None = None,
) -> type[SimpleHTTPRequestHandler]:
    session_store = sessions or TtsSessionStore()

    class BooksiteRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(build_dir or Path.cwd()), **kwargs)

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
            route = self.path.partition("?")[0]
            if route == "/api/tts/status":
                try:
                    self._require_loopback()
                    self._send_json(200, engine.status())
                except RequestError as error:
                    self._send_json(error.status, {"error": str(error)})
                return
            stream_prefix = "/api/tts/stream/"
            if route.startswith(stream_prefix):
                self._stream_tts(route.removeprefix(stream_prefix))
                return
            if build_dir is None:
                self._send_json(404, {"error": "此端口仅提供本地语音接口。"})
                return
            super().do_GET()

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
                engine.require_available()
                token = session_store.create(text)
                self._send_json(201, {"streamUrl": f"/api/tts/stream/{token}"})
            except RequestError as error:
                self._send_json(error.status, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:
                print(f"Qwen3-TTS error: {error}", file=sys.stderr, flush=True)
                self._send_json(500, {"error": "本地语音生成失败，请查看启动窗口中的错误。"})

        def _stream_tts(self, token: str) -> None:
            chunks: Iterator[bytes] | None = None
            headers_sent = False
            try:
                self._require_loopback()
                text = session_store.consume(token)
                chunks = engine.stream_pcm(text)
                first_chunk = next(chunks)
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Connection", "close")
                self.end_headers()
                headers_sent = True
                self.close_connection = True
                self.wfile.write(wav_stream_header(sample_rate=engine.sample_rate))
                self.wfile.write(first_chunk)
                self.wfile.flush()
                for chunk in chunks:
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except StopIteration:
                if not headers_sent:
                    self._send_json(500, {"error": "语音模型没有返回音频。"})
            except RequestError as error:
                if not headers_sent:
                    self._send_json(error.status, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:
                print(f"Qwen3-TTS stream error: {error}", file=sys.stderr, flush=True)
                if not headers_sent:
                    self._send_json(
                        500,
                        {"error": "本地语音生成失败，请查看启动窗口中的错误。"},
                    )
            finally:
                if chunks is not None:
                    chunks.close()

    return BooksiteRequestHandler


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview a book site or serve local Qwen3-TTS.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument(
        "--tts-only",
        action="store_true",
        help="Serve only the loopback TTS API without requiring a Docusaurus build.",
    )
    parser.add_argument(
        "--tts-backend",
        choices=("auto", "mlx", "torch"),
        default="auto",
        help="Select the local Qwen runtime. Auto uses MLX on macOS and PyTorch elsewhere.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    if not is_loopback_client(args.host):
        raise SystemExit("为保护本地语音接口，--host 必须是 127.0.0.1 或 ::1。")
    build_dir = None if args.tts_only else Path(__file__).resolve().parent / "build"
    if build_dir is not None and not (build_dir / "index.html").is_file():
        raise SystemExit(
            "未找到 build/index.html。请先运行 PDF 转换，或在本书目录执行 pnpm build。"
        )

    engine = create_tts_engine(backend=args.tts_backend)
    handler = make_handler(build_dir, engine)
    try:
        server = BooksiteServer((args.host, args.port), handler)
    except OSError as error:
        raise SystemExit(
            f"无法启动本地网站：{error}。可尝试 python3 serve-local.py --port 8001"
        ) from error

    url = f"http://{args.host}:{server.server_port}/"
    label = "本地语音服务" if args.tts_only else "本地网站"
    print(f"{label}：{url}", flush=True)
    if engine.status()["available"]:
        print("Qwen3-TTS 正在后台预热；接口已经可连接。", flush=True)
        start_background_warm_up(engine)
    print("保持此窗口开启；按 Control-C 停止。", flush=True)
    if not args.no_open and not args.tts_only:
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
