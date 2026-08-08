import json
import os
import subprocess
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from booksite.site.local_server import (
    BooksiteServer,
    audio_to_pcm16_bytes,
    make_handler,
    parse_args,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = PROJECT_ROOT / "browser-extension"


class _FakeExtensionEngine:
    sample_rate = 24_000

    def status(self) -> dict[str, object]:
        return {"available": True, "model": "fake", "runtime": True}

    def require_available(self) -> None:
        return

    def stream_pcm(self, text: str):
        del text
        yield audio_to_pcm16_bytes([0.0, 0.25, -0.25, 0.0])


def test_extension_manifest_uses_minimal_loopback_permissions() -> None:
    manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert manifest["version"] == "0.2.0"
    assert manifest["permissions"] == ["offscreen"]
    assert manifest["host_permissions"] == [
        "http://127.0.0.1:8765/*",
        "http://localhost:8765/*",
    ]
    assert manifest["content_scripts"][0]["matches"] == ["http://*/*", "https://*/*"]
    assert manifest["background"] == {
        "service_worker": "background.js",
        "type": "module",
    }
    assert "<all_urls>" not in json.dumps(manifest)


def test_extension_artifacts_are_local_safe_and_streaming() -> None:
    expected_files = {
        "audio-engine.js",
        "background.js",
        "content.css",
        "content.js",
        "manifest.json",
        "offscreen.html",
        "offscreen.js",
        "page-reader.js",
        "popup.html",
        "popup.js",
        "reading-queue.js",
        "安装说明.md",
        "启动Qwen朗读服务.command",
    }

    assert expected_files <= {path.name for path in EXTENSION_DIR.iterdir()}
    scripts = "\n".join(
        (EXTENSION_DIR / name).read_text(encoding="utf-8")
        for name in (
            "audio-engine.js",
            "background.js",
            "content.js",
            "offscreen.js",
            "page-reader.js",
            "popup.js",
            "reading-queue.js",
        )
    )
    assert "http://127.0.0.1:8765" in scripts
    assert "attachShadow({mode: 'open'})" in scripts
    assert "CSS.highlights.set" in scripts
    assert "event.code === 'Space'" in scripts
    assert "streamResponse.body.getReader()" in scripts
    assert "new AudioContext()" in scripts
    assert "linearRampToValueAtTime" in scripts
    assert "waitForBufferCapacity" in scripts
    assert "gainNode.disconnect()" in scripts
    assert "sender.url === chrome.runtime.getURL(OFFSCREEN_URL)" in scripts
    assert "event.composedPath().some" in scripts
    assert "innerHTML" not in scripts
    assert "eval(" not in scripts
    assert "https://" not in scripts
    launcher = (EXTENSION_DIR / "启动Qwen朗读服务.command").read_text(encoding="utf-8")
    assert "--tts-only" in launcher
    assert "--port 8765" in launcher


def test_reading_queue_normalizes_boundaries_and_enforces_limits() -> None:
    queue_script = EXTENSION_DIR / "reading-queue.js"
    runner = f"""
const fs = require('node:fs');
const vm = require('node:vm');
const context = {{Intl}};
vm.createContext(context);
vm.runInContext(fs.readFileSync({json.dumps(str(queue_script))}, 'utf8'), context);
const queue = context.QwenReadingQueue;
const items = queue.segmentText('These applications work.  第二句。', 10);
if (items.length !== 2) throw new Error(`expected 2 items, got ${{items.length}}`);
if (items[0].text !== 'applications work.') throw new Error(items[0].text);
if (items[1].text !== '第二句。') throw new Error(items[1].text);
if (queue.snapStartToWordBoundary('These applications work.', 5) !== 5) {{
  throw new Error('word boundary moved');
}}
if (queue.snapStartToWordBoundary('中文朗读。', 2) !== 2) {{
  throw new Error('CJK boundary moved');
}}
const oversized = queue.segmentText('x'.repeat(2100), 0);
if (oversized.some((item) => item.text.length > 2000)) {{
  throw new Error('oversized sentence was not split');
}}
"""
    result = subprocess.run(
        ["node", "--eval", runner],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_offscreen_restarts_current_sentence_after_audio_document_was_discarded() -> None:
    offscreen_script = EXTENSION_DIR / "offscreen.js"
    runner = f"""
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync({json.dumps(str(offscreen_script))}, 'utf8').replace(
  "import {{StreamingTtsPlayer}} from './audio-engine.js';",
  `
  class StreamingTtsPlayer {{
    constructor() {{
      this.startCalls = [];
      globalThis.testPlayer = this;
    }}
    async start(items, options) {{
      this.startCalls.push({{items, options}});
      options.onSentenceStarted(0);
      return new Promise(() => {{}});
    }}
    async pause() {{}}
    async resume() {{ return false; }}
    setSpeed() {{}}
    stop() {{}}
  }}
  `,
);
const listeners = [];
const emitted = [];
const context = {{
  chrome: {{
    runtime: {{
      onMessage: {{addListener(listener) {{ listeners.push(listener); }}}},
      sendMessage(message) {{
        emitted.push(message);
        return Promise.resolve();
      }},
    }},
  }},
}};
vm.createContext(context);
vm.runInContext(source, context);

listeners[0]({{
  target: 'offscreen',
  type: 'RESUME_READING',
  sessionId: 'long-pause-session',
  tabId: 7,
  continuous: true,
  items: [{{text: 'Current sentence.'}}, {{text: 'Next sentence.'}}],
  indexOffset: 4,
  speed: 1,
}});

setImmediate(() => {{
  if (context.testPlayer.startCalls.length !== 1) {{
    throw new Error('discarded audio document did not rebuild playback');
  }}
  const started = emitted.find((message) => message.event === 'SENTENCE_STARTED');
  if (!started || started.index !== 4) {{
    throw new Error(`expected restored sentence index 4, got ${{started?.index}}`);
  }}
}});
"""
    result = subprocess.run(
        ["node", "--eval", runner],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_background_requires_a_bounded_queue_for_long_pause_recovery() -> None:
    background_script = EXTENSION_DIR / "background.js"
    runner = f"""
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = [];
const forwarded = [];
const context = {{
  chrome: {{
    offscreen: {{
      hasDocument() {{ return Promise.resolve(true); }},
      createDocument() {{ return Promise.resolve(); }},
    }},
    runtime: {{
      id: 'test-extension',
      getURL(path) {{ return `chrome-extension://test-extension/${{path}}`; }},
      onMessage: {{addListener(listener) {{ listeners.push(listener); }}}},
      sendMessage(message) {{
        forwarded.push(message);
        return Promise.resolve();
      }},
    }},
    tabs: {{sendMessage() {{ return Promise.resolve(); }}}},
  }},
}};
vm.createContext(context);
vm.runInContext(
  fs.readFileSync({json.dumps(str(background_script))}, 'utf8'),
  context,
);

const sender = {{tab: {{id: 12}}}};
const invalidAccepted = listeners[0](
  {{
    target: 'background',
    type: 'RESUME_READING',
    sessionId: 'long-pause-session',
  }},
  sender,
  () => {{}},
);
if (invalidAccepted !== false) {{
  throw new Error('resume without a recovery queue was accepted');
}}

const validAccepted = listeners[0](
  {{
    target: 'background',
    type: 'RESUME_READING',
    sessionId: 'long-pause-session',
    continuous: true,
    items: [{{text: 'Current sentence.'}}, {{text: 'Next sentence.'}}],
    indexOffset: 4,
    speed: 1,
  }},
  sender,
  () => {{}},
);
if (validAccepted !== true) {{
  throw new Error('bounded long-pause recovery queue was rejected');
}}

setImmediate(() => {{
  if (forwarded.length !== 1 || forwarded[0].target !== 'offscreen') {{
    throw new Error('valid recovery message was not forwarded once');
  }}
}});
"""
    result = subprocess.run(
        ["node", "--eval", runner],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_audio_stream_retries_when_recovery_races_a_busy_model() -> None:
    audio_engine = EXTENSION_DIR / "audio-engine.js"
    runner = f"""
const {{pathToFileURL}} = require('node:url');

(async () => {{
  const moduleUrl = pathToFileURL({json.dumps(str(audio_engine))});
  moduleUrl.searchParams.set('test', String(Date.now()));
  const engine = await import(moduleUrl.href);
  let requestCount = 0;
  const streamResponse = await engine.requestAudioStream('Resume this sentence.', {{
    request: async () => {{
      requestCount += 1;
      if (requestCount === 1) {{
        return new Response(
          JSON.stringify({{streamUrl: '/api/tts/stream/first-attempt'}}),
          {{status: 201, headers: {{'Content-Type': 'application/json'}}}},
        );
      }}
      if (requestCount === 2) {{
        return new Response(
          JSON.stringify({{error: 'busy'}}),
          {{status: 409, headers: {{'Content-Type': 'application/json'}}}},
        );
      }}
      if (requestCount === 3) {{
        return new Response(
          JSON.stringify({{streamUrl: '/api/tts/stream/recovered'}}),
          {{status: 201, headers: {{'Content-Type': 'application/json'}}}},
        );
      }}
      return new Response(new Uint8Array([82, 73, 70, 70]), {{status: 200}});
    }},
    retryDelays: [0],
    signal: new AbortController().signal,
  }});
  if (requestCount !== 4) {{
    throw new Error(`expected 4 requests, got ${{requestCount}}`);
  }}
  if (streamResponse.status !== 200 || !streamResponse.body) {{
    throw new Error('recovered stream response was not returned');
  }}
}})().catch((error) => {{
  console.error(error);
  process.exitCode = 1;
}});
"""
    result = subprocess.run(
        ["node", "--eval", runner],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_audio_stream_retries_a_transient_failed_fetch() -> None:
    audio_engine = EXTENSION_DIR / "audio-engine.js"
    runner = f"""
const {{pathToFileURL}} = require('node:url');

(async () => {{
  const moduleUrl = pathToFileURL({json.dumps(str(audio_engine))});
  moduleUrl.searchParams.set('test', String(Date.now()));
  const engine = await import(moduleUrl.href);
  let requestCount = 0;
  const streamResponse = await engine.requestAudioStream('Retry this sentence.', {{
    request: async () => {{
      requestCount += 1;
      if (requestCount === 1) throw new TypeError('Failed to fetch');
      if (requestCount === 2) {{
        return new Response(
          JSON.stringify({{streamUrl: '/api/tts/stream/recovered'}}),
          {{status: 201, headers: {{'Content-Type': 'application/json'}}}},
        );
      }}
      return new Response(new Uint8Array([82, 73, 70, 70]), {{status: 200}});
    }},
    retryDelays: [0],
    signal: new AbortController().signal,
  }});
  if (requestCount !== 3) throw new Error(`expected 3 requests, got ${{requestCount}}`);
  if (streamResponse.status !== 200) throw new Error('transient Fetch failure did not recover');
}})().catch((error) => {{
  console.error(error);
  process.exitCode = 1;
}});
"""
    result = subprocess.run(
        ["node", "--eval", runner],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_audio_stream_replaces_failed_fetch_with_actionable_guidance() -> None:
    audio_engine = EXTENSION_DIR / "audio-engine.js"
    runner = f"""
const {{pathToFileURL}} = require('node:url');

(async () => {{
  const moduleUrl = pathToFileURL({json.dumps(str(audio_engine))});
  moduleUrl.searchParams.set('test', String(Date.now()));
  const engine = await import(moduleUrl.href);
  try {{
    await engine.requestAudioStream('Unavailable service.', {{
      request: async () => {{ throw new TypeError('Failed to fetch'); }},
      retryDelays: [0, 0],
      signal: new AbortController().signal,
    }});
    throw new Error('unavailable service unexpectedly succeeded');
  }} catch (error) {{
    if (error.message.includes('Failed to fetch')) throw error;
    if (!error.message.includes('启动Qwen朗读服务.command')) throw error;
  }}
}})().catch((error) => {{
  console.error(error);
  process.exitCode = 1;
}});
"""
    result = subprocess.run(
        ["node", "--eval", runner],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_stream_reader_applies_backpressure_while_audio_clock_is_paused() -> None:
    audio_engine = EXTENSION_DIR / "audio-engine.js"
    runner = f"""
const {{pathToFileURL}} = require('node:url');

class FakeAudioContext {{
  constructor() {{ this.currentTime = 0; this.destination = {{}}; this.state = 'running'; }}
  async resume() {{ this.state = 'running'; }}
  async close() {{ this.state = 'closed'; }}
  createBuffer(channels, length, sampleRate) {{
    return {{duration: length / sampleRate, copyToChannel() {{}}}};
  }}
  createBufferSource() {{
    return {{
      playbackRate: {{value: 1}}, connect() {{}}, disconnect() {{}}, start() {{}}, stop() {{}},
      onended: null, buffer: null,
    }};
  }}
  createGain() {{
    return {{
      connect() {{}}, disconnect() {{}},
      gain: {{setValueAtTime() {{}}, linearRampToValueAtTime() {{}}}},
    }};
  }}
}}
globalThis.AudioContext = FakeAudioContext;
let pcmChunksRead = 0;
globalThis.fetch = async (url) => {{
  if (url.endsWith('/api/tts')) {{
    return new Response(
      JSON.stringify({{streamUrl: '/api/tts/stream/test'}}),
      {{status: 201, headers: {{'Content-Type': 'application/json'}}}},
    );
  }}
  return new Response(new ReadableStream({{
    pull(controller) {{
      if (pcmChunksRead >= 30) {{ controller.close(); return; }}
      const size = pcmChunksRead === 0 ? 48044 : 48000;
      pcmChunksRead += 1;
      controller.enqueue(new Uint8Array(size));
    }},
  }}), {{status: 200}});
}};

(async () => {{
  const moduleUrl = pathToFileURL({json.dumps(str(audio_engine))});
  moduleUrl.searchParams.set('test', String(Date.now()));
  const {{StreamingTtsPlayer}} = await import(moduleUrl.href);
  const player = new StreamingTtsPlayer();
  const playback = player.start([{{text: 'A long sentence.'}}], {{
    speed: 1,
    onSentenceStarted() {{}},
  }}).catch((error) => {{
    if (error.name !== 'AbortError') throw error;
  }});
  await new Promise((resolve) => setTimeout(resolve, 150));
  const failure = pcmChunksRead > 12
    ? new Error(`paused clock consumed ${{pcmChunksRead}} seconds of audio without backpressure`)
    : null;
  player.stop();
  await playback;
  if (failure) throw failure;
}})().catch((error) => {{
  console.error(error);
  process.exitCode = 1;
}});
"""
    result = subprocess.run(
        ["node", "--eval", runner],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(os.name == "nt", reason="POSIX launcher is covered on macOS and Linux")
def test_service_launcher_restarts_once_after_an_unexpected_exit(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    counter = tmp_path / "attempts"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        """#!/bin/sh
count=0
if [ -f "$BOOKSITE_TTS_TEST_COUNTER" ]; then count=$(cat "$BOOKSITE_TTS_TEST_COUNTER"); fi
count=$((count + 1))
printf '%s' "$count" > "$BOOKSITE_TTS_TEST_COUNTER"
if [ "$count" -eq 1 ]; then exit 1; fi
exit 0
""",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    launcher = EXTENSION_DIR / "启动Qwen朗读服务.command"
    environment = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "BOOKSITE_TTS_RESTART_DELAY": "0",
        "BOOKSITE_TTS_TEST_COUNTER": str(counter),
    }

    result = subprocess.run(
        [str(launcher)],
        capture_output=True,
        text=True,
        check=False,
        env=environment,
        timeout=5,
    )

    assert result.returncode == 0, result.stderr
    assert counter.read_text(encoding="utf-8") == "2"
    assert "正在自动重启" in result.stderr


def test_tts_only_mode_does_not_require_a_docusaurus_build(tmp_path: Path) -> None:
    engine = _FakeExtensionEngine()
    server = BooksiteServer(("127.0.0.1", 0), make_handler(None, engine))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    request = Request(
        f"{base_url}/api/tts",
        data=json.dumps({"text": "Read any website."}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(f"{base_url}/api/tts/status", timeout=3) as response:
            assert json.load(response)["available"] is True
        with urlopen(request, timeout=3) as response:
            stream_url = json.load(response)["streamUrl"]
        with urlopen(f"{base_url}{stream_url}", timeout=3) as response:
            assert response.read().startswith(b"RIFF")
        try:
            urlopen(f"{base_url}/", timeout=3)
        except HTTPError as error:
            assert error.code == 404
            assert json.load(error)["error"] == "此端口仅提供本地语音接口。"
        else:
            raise AssertionError("TTS-only server unexpectedly served a website")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_tts_only_cli_contract() -> None:
    args = parse_args(["--tts-only", "--port", "8765", "--no-open"])

    assert args.tts_only is True
    assert args.port == 8765
    assert args.no_open is True
