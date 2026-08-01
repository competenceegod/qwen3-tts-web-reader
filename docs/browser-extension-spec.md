# Spec: Qwen3-TTS 通用网页朗读扩展

## Objective

Build an unpacked Chrome/Chromium Manifest V3 extension that adds the existing
local Qwen3-TTS reading experience to ordinary web documents. A user can select
text on an HTTP or HTTPS page, choose one-off or continuous reading, and keep
the active sentence highlighted and vertically centered while it is spoken.

Assumptions approved by the user's request and existing workflow:

- Chrome/Chromium is the first supported browser.
- The extension reuses PDFgear's existing local Qwen3-TTS model.
- Ordinary HTTP and HTTPS documents are in scope. Browser-internal pages,
  extension stores, and other pages where Chrome forbids content scripts are
  not.
- Continuous reading keeps the existing Space pause/resume behavior.
- The local service is started separately and remains bound to loopback only.

This reliability revision makes the extension the single owner of speech for
both ordinary pages and generated PDF book sites. Generated sites must not
embed a second reader, TTS API, model runtime, or speech-specific launcher.
The extension must recover from a temporarily unavailable local service, keep
continuous playback resource usage bounded, and resume after a pause longer
than Chrome's 30-second offscreen-audio lifetime.

## Tech stack

- Chrome Extension Manifest V3
- Dependency-free JavaScript, HTML, and CSS
- Shadow DOM for extension controls
- CSS Custom Highlight API with a DOM-range fallback
- Existing Python `local_server.py` and MLX-Audio runtime
- pytest plus Node's built-in VM for deterministic queue tests

## Commands

```bash
# Python and artifact tests
uv run --frozen pytest tests/integration/test_browser_extension.py
uv run --frozen pytest
uv run --frozen ruff check .

# Start the extension-only local TTS service
open browser-extension/启动Qwen朗读服务.command

# Install for development
# chrome://extensions → Developer mode → Load unpacked
# Select: /Users/conermoltbot/Documents/pdf-book-site/browser-extension
```

## Project structure

```text
browser-extension/
  manifest.json                 Extension permissions and entry points
  background.js                 Offscreen lifecycle and tab message relay
  offscreen.html                Hidden audio document
  offscreen.js                  Streaming Web Audio queue
  reading-queue.js              Deterministic sentence boundary helpers
  content.js                    Selection, ranges, highlights, controls
  content.css                   Host container and highlight styling
  popup.html / popup.js         Service status and setup guidance
  启动Qwen朗读服务.command        Standalone loopback service launcher
  安装说明.md                    Installation and known limitations
src/booksite/site/local_server.py
                                Extension-only loopback TTS server
tests/integration/test_browser_extension.py
                                Manifest, security, queue, and launcher tests
```

## Code style

Use explicit message names, validate every message at its receiving boundary,
and keep page DOM data in the content script:

```js
chrome.runtime.sendMessage({
  target: 'background',
  type: 'START_READING',
  sessionId,
  items: queue.map(({text}) => ({text})),
  speed,
});
```

No page text may be interpolated into HTML. Controls use `textContent`, created
DOM nodes, and fixed message strings.

## Interface contract

Content script to background:

- `START_READING`: `sessionId`, `items[{text}]`, `speed`
- `PAUSE_READING`, `RESUME_READING`, `STOP_READING`
- `SET_SPEED`: numeric `speed`

Background to offscreen adds the originating `tabId`. Offscreen to content
emits:

- `STATE_CHANGED`: `state`, `message`
- `SENTENCE_STARTED`: `index`
- `READING_FINISHED`
- `READING_ERROR`: safe user-facing `message`

Every message includes `target` and `sessionId`. Unknown targets, message types,
missing identifiers, invalid indices, invalid speed values, and oversized
queues are ignored or rejected.

## Testing strategy

- Pure queue tests verify Latin mid-word starts, CJK boundaries, sentence
  ordering, whitespace cleanup, per-item limits, and total queue limits.
- Artifact tests verify Manifest V3, minimum host permissions, no remote code,
  no `eval`, no unsafe `innerHTML`, Shadow DOM isolation, loopback-only API
  URLs, streamed audio, pause/resume, highlighting, and the standalone launcher.
- HTTP integration tests run the existing fake TTS engine with no Docusaurus
  build directory and verify the status, create-session, and WAV stream API.
- Browser acceptance uses an isolated Chrome profile with the unpacked
  extension on at least two structurally different pages. Console errors,
  selection controls, sentence progress, Space pause/resume, and stop cleanup
  are checked.
- Reliability tests inject a refused network request followed by recovery,
  hold Web Audio's clock still to prove stream backpressure, and verify that an
  unexpected local-service exit is restarted by the launcher.
- A browser acceptance run pauses continuous reading for more than 30 seconds,
  then resumes from the current sentence and continues without a raw Fetch
  exception.

## Boundaries

### Always

- Treat every page and every extension message as untrusted input.
- Keep host permissions restricted to the two loopback TTS origins.
- Keep selected text in memory only and send it only to the local service.
- Render controls inside a Shadow DOM and construct UI with DOM APIs.
- Abort network streams and disconnect audio nodes on stop or navigation.
- Bound each sentence, queue length, and total queued characters.
- Open the loopback HTTP port before model warm-up and expose warm-up state so
  the browser never mistakes model initialization for a missing service.
- Retry transient network failures and model-busy responses with bounded
  backoff; convert exhausted Fetch failures into actionable Chinese guidance.
- Apply response-stream backpressure whenever scheduled audio reaches the
  buffer-ahead limit, including while playback is paused.

### Ask first

- Supporting cloud TTS or sending selected text off-device.
- Expanding host permissions beyond loopback.
- Adding CORS wildcard origins to the local service.
- Publishing the extension to a browser store.
- Installing the unpacked extension into the user's primary Chrome profile.

### Never

- Request browsing history, cookies, tabs, clipboard, or broad network access.
- Read password inputs, editable controls, hidden content, scripts, or styles.
- Execute page-provided strings as code or HTML.
- Run on `chrome://`, extension-store, or other restricted pages.
- Bind the TTS service to a non-loopback interface.
- Add a second TTS reader, MLX dependency, or speech API to generated PDF
  sites; those sites are ordinary pages consumed by this extension.

## Success criteria

- Loading the unpacked extension adds selection controls to ordinary HTTP and
  HTTPS documents without changing their layout.
- “朗读选中” reads only selected text; “从此处连续朗读” builds an ordered
  queue from the complete word containing the selection start to the end of
  the document's main readable region.
- The active sentence is highlighted and centered when playback actually
  starts, not while it is only being prefetched.
- Space pauses and resumes an active continuous session unless focus is in an
  editable or interactive control. Escape stops playback.
- A paused session remains recoverable after Chrome discards the silent
  offscreen audio document. Resuming recreates the document when necessary and
  restarts at the current sentence before continuing through the remaining
  in-memory queue; selected page text is not persisted to disk.
- Pausing for at least 30 seconds and then pressing Space returns to `playing`
  without losing the remaining queue. If the audio document or local stream
  was discarded, the current sentence is regenerated automatically.
- Audio uses a gapless timeline, startup buffer, bounded sentence prefetch,
  sentence crossfade, and deterministic cleanup inside the extension.
- The local status endpoint becomes reachable before model warm-up completes;
  a native-runtime crash is restarted by the launcher, while a normal
  Control-C exit is not restarted.
- Newly generated PDF sites contain no `SelectionTtsReader`, `/api/tts`
  frontend request, or MLX-aware site launcher. Existing generated sites are
  migrated to the same extension-only ownership model.
- A transient connection refusal or HTTP 409 is retried without displaying
  `Failed to fetch`. After the bounded retry budget is exhausted, the UI shows
  how to start the local Qwen service.
- The extension can fetch only `http://127.0.0.1:8765/*` and
  `http://localhost:8765/*`.
- The standalone service works without `build/index.html` and still rejects
  non-loopback clients, malformed input, oversized input, expired streams, and
  concurrent inference.
- All tests, Ruff, extension syntax checks, and isolated-browser acceptance
  checks pass.

## Open questions

Firefox/Safari packaging, Chrome Web Store publication, automatic login-item
startup, and reading across iframe or pagination boundaries are deferred.
