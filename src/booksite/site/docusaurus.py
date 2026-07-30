from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from pathlib import Path

from booksite.models.book_ir import BookIR

_PDF_EMBEDDED_COMPONENT = re.compile(
    r"<(?P<component>PdfCodeBlock|PdfUrlCallout)\b[^>]*"
    r"\bdata=(?P<quote>[\"'])(?P<data>.*?)(?P=quote)[^>]*/?>"
)


@dataclass(frozen=True, slots=True)
class SiteGenerationResult:
    site_dir: Path
    docs_dir: Path
    document_paths: tuple[Path, ...]


def _js_string(value: str | None) -> str:
    return json.dumps(value or "Converted Book", ensure_ascii=True)


def _pdf_code_search_text(match: re.Match[str]) -> str:
    try:
        payload = json.loads(base64.b64decode(match.group("data"), validate=True).decode("utf-8"))
        lines = payload["lines"]
        if not isinstance(lines, list):
            return " "
        code_lines = []
        for line in lines:
            if not isinstance(line, list):
                return " "
            code_lines.append(
                "".join(
                    span["text"]
                    for span in line
                    if isinstance(span, dict) and isinstance(span.get("text"), str)
                )
            )
        return f" {' '.join(code_lines)} "
    except (
        binascii.Error,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return " "


def _pdf_url_search_text(match: re.Match[str]) -> str:
    try:
        payload = json.loads(base64.b64decode(match.group("data"), validate=True).decode("utf-8"))
        prefix = payload["prefix"]
        url = payload["url"]
        suffix = payload["suffix"]
        if not all(isinstance(value, str) for value in (prefix, url, suffix)):
            return " "
        return f" {prefix}{url}{suffix} "
    except (
        binascii.Error,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return " "


def _plain_markdown_fragment(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    return re.sub(r"[#>*_`|~-]+", " ", text)


def _plain_search_text(markdown: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _PDF_EMBEDDED_COMPONENT.finditer(markdown):
        parts.append(_plain_markdown_fragment(markdown[cursor : match.start()]))
        parts.append(
            _pdf_code_search_text(match)
            if match.group("component") == "PdfCodeBlock"
            else _pdf_url_search_text(match)
        )
        cursor = match.end()
    parts.append(_plain_markdown_fragment(markdown[cursor:]))
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _search_index_json(book: BookIR) -> str:
    entries = [
        {
            "title": section.title,
            "url": "/" if index == 0 else f"/{section.slug}",
            "pages": section.source_pages,
            "text": _plain_search_text(section.markdown),
        }
        for index, section in enumerate(book.sections)
    ]
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n"


def _frontmatter(book: BookIR, index: int) -> str:
    section = book.sections[index]
    previous_id = book.sections[index - 1].section_id if index > 0 else None
    next_id = book.sections[index + 1].section_id if index + 1 < len(book.sections) else None
    lines = [
        "---",
        f"id: {section.section_id}",
        f"title: {json.dumps(section.title, ensure_ascii=False)}",
        f"sidebar_position: {section.order}",
        f"slug: {'/' if index == 0 else '/' + section.slug}",
        "toc_min_heading_level: 2",
        "toc_max_heading_level: 5",
    ]
    if previous_id:
        lines.append(f"pagination_prev: {previous_id}")
    if next_id:
        lines.append(f"pagination_next: {next_id}")
    return "\n".join([*lines, "---", ""])


def _package_json() -> str:
    package = {
        "name": "generated-booksite",
        "version": "0.1.0",
        "private": True,
        "scripts": {
            "start": "docusaurus start",
            "build": "docusaurus build && python3 cleanup-build.py",
            "serve": "docusaurus serve",
            "clear": "docusaurus clear",
        },
        "dependencies": {
            "@docusaurus/core": "3.10.2",
            "@docusaurus/preset-classic": "3.10.2",
            "@mdx-js/react": "^3.0.0",
            "clsx": "^2.0.0",
            "katex": "0.16.22",
            "prism-react-renderer": "^2.3.0",
            "react": "^19.0.0",
            "react-dom": "^19.0.0",
            "rehype-katex": "7.0.1",
            "remark-math": "6.0.0",
        },
        "devDependencies": {
            "@docusaurus/module-type-aliases": "3.10.2",
            "@docusaurus/types": "3.10.2",
        },
        "engines": {"node": ">=20.0"},
    }
    return json.dumps(package, ensure_ascii=False, indent=2) + "\n"


def _cleanup_build_py() -> str:
    return '''#!/usr/bin/env python3
"""Remove static image copies after Docusaurus emitted hashed equivalents."""

from pathlib import Path
import shutil

assets_dir = Path(__file__).resolve().parent / "build" / "assets"
if assets_dir.is_dir():
    for candidate in assets_dir.iterdir():
        if candidate.is_dir() and (candidate / ".booksite-generated").is_file():
            shutil.rmtree(candidate)
'''


def _pdf_code_block_js() -> str:
    return """import React, {useMemo, useState} from 'react';

export default function PdfCodeBlock({data}) {
  const [copied, setCopied] = useState(false);
  const code = useMemo(() => JSON.parse(atob(data)), [data]);
  const plainText = useMemo(
    () => code.lines
      .map((line) => line.map((span) => span.text).join('').replace(/[ \\t]+$/u, ''))
      .join('\\n'),
    [code],
  );

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(plainText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div
      className="booksite-pdf-code"
      style={{
        '--pdf-code-background': code.backgroundColor,
        '--pdf-code-border': code.borderColor,
        '--pdf-code-font-size': `${code.fontSizePt}pt`,
      }}
    >
      <button
        type="button"
        aria-label={copied ? 'Code copied' : 'Copy code'}
        aria-live="polite"
        onClick={copyCode}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
      <pre tabIndex={0}>
        <code>
          {code.lines.map((line, lineIndex) => (
            <React.Fragment key={lineIndex}>
              {line.map((span, spanIndex) => (
                <span
                  key={spanIndex}
                  style={{
                    color: span.color,
                    fontFamily:
                      `"${span.fontFamily}", Consolas, "SFMono-Regular", Menlo, monospace`,
                    fontSize: `${span.fontSizePt}pt`,
                    fontStyle: span.italic ? 'italic' : 'normal',
                    fontWeight: span.bold ? 700 : 400,
                  }}
                >
                  {span.text}
                </span>
              ))}
              {lineIndex + 1 < code.lines.length ? '\\n' : null}
            </React.Fragment>
          ))}
        </code>
      </pre>
    </div>
  );
}
"""


def _pdf_url_callout_js() -> str:
    return """import React, {useMemo} from 'react';

export default function PdfUrlCallout({data}) {
  const callout = useMemo(() => JSON.parse(atob(data)), [data]);

  return (
    <aside
      className="booksite-pdf-url-callout"
      aria-label="Source link"
      style={{
        '--pdf-callout-background': callout.backgroundColor,
        '--pdf-callout-border': callout.borderColor,
      }}
    >
      <span>{callout.prefix}</span>
      <a href={callout.url} rel="noreferrer">
        <code>{callout.url}</code>
      </a>
      <span>{callout.suffix}</span>
    </aside>
  );
}
"""


def _mdx_components_js() -> str:
    return """import MDXComponents from '@theme-original/MDXComponents';
import PdfCodeBlock from '@site/src/components/PdfCodeBlock';
import PdfUrlCallout from '@site/src/components/PdfUrlCallout';

export default {
  ...MDXComponents,
  PdfCodeBlock,
  PdfUrlCallout,
};
"""


def _preview_server_py() -> str:
    return Path(__file__).with_name("local_server.py").read_text(encoding="utf-8")


def _preview_launcher_sh() -> str:
    return """#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project --python 3.12 --with 'mlx-audio==0.4.5' \
    python "$SCRIPT_DIR/serve-local.py"
fi

echo "提示：未找到 uv，将仅启动网站；Qwen3-TTS 朗读暂不可用。" >&2
exec /usr/bin/env python3 "$SCRIPT_DIR/serve-local.py"
"""


def _preview_guide_text() -> str:
    return """本地打开生成的网站
====================

不要直接双击 build/index.html。Docusaurus 的静态资源和页面路由需要通过
HTTP 访问；file:// 协议会导致 CSS、JavaScript 和章节链接加载失败。

macOS：
1. 双击“打开网站.command”。
2. 默认浏览器会自动打开本地网站。
3. 阅读期间保持终端窗口开启；按 Control-C 停止。

Qwen3-TTS 朗读：
1. 启动脚本会复用 PDFgear 已下载的 Qwen3-TTS 模型，不会再复制模型。
2. 第一次启动可能需要通过 uv 安装约 100 MB 的 MLX 运行库。
3. 选择文字后，可以只朗读选中内容，或从选择位置连续朗读到当前文档末尾。
4. 连续朗读会高亮并居中当前句；按空格键暂停或继续，也可停止和调速。
5. 文字和语音只在本机处理，本地接口只接受 127.0.0.1/::1 请求。
6. 若未安装 uv，网站仍可正常阅读，但朗读功能不可用。

命令行：
uv run --no-project --python 3.12 --with 'mlx-audio==0.4.5' python serve-local.py

开发者也可以运行：
pnpm serve

部署时请上传 build/ 目录中的全部内容，不要把 baseUrl 改成本机文件路径。
"""


def _reading_queue_js() -> str:
    return """
const MAX_TEXT_CHARACTERS = 2000;
const HIGHLIGHT_NAME = 'booksite-tts-current';
const BLOCK_SELECTOR = 'p, li, h1, h2, h3, h4, h5, h6, pre, blockquote, td, th, figcaption';
const SKIPPED_SELECTOR = [
  'button',
  'input',
  'textarea',
  'select',
  'script',
  'style',
  '.hash-link',
  '[aria-hidden="true"]',
].join(', ');

export function clearReadingHighlight() {
  CSS.highlights?.delete(HIGHLIGHT_NAME);
}

export function selectionDetails() {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const text = selection.toString().replace(/\\s+/gu, ' ').trim();
  if (!text || text.length > MAX_TEXT_CHARACTERS) return null;
  const range = selection.getRangeAt(0);
  const node = range.commonAncestorContainer;
  const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
  if (!element?.closest('.theme-doc-markdown')) return null;
  const rect = range.getBoundingClientRect();
  if (!rect.width && !rect.height) return null;
  return {
    text,
    range: range.cloneRange(),
    top: Math.max(12, rect.top - 52),
    left: Math.max(
      12,
      Math.min(window.innerWidth - 300, rect.left + rect.width / 2 - 142),
    ),
  };
}

function readableTextNodes(article) {
  const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.data.trim() || node.parentElement?.closest(SKIPPED_SELECTOR)) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  return nodes;
}

function readingDocument(article) {
  const segments = [];
  let text = '';
  let previousBlock = null;
  for (const node of readableTextNodes(article)) {
    const block = node.parentElement?.closest(BLOCK_SELECTOR);
    if (text) {
      if (block !== previousBlock) text += '\\n';
      else if (!/\\s$/u.test(text) && !/^\\s/u.test(node.data)) text += ' ';
    }
    const start = text.length;
    text += node.data;
    segments.push({node, start, end: text.length});
    previousBlock = block;
  }
  return {text, segments};
}

function selectionStartOffset(range, segments) {
  const exact = segments.find((segment) => segment.node === range.startContainer);
  if (exact) {
    return exact.start + Math.min(range.startOffset, exact.node.data.length);
  }
  const collapsed = range.cloneRange();
  collapsed.collapse(true);
  for (const segment of segments) {
    const nodeRange = document.createRange();
    nodeRange.selectNodeContents(segment.node);
    if (collapsed.compareBoundaryPoints(Range.START_TO_END, nodeRange) <= 0) {
      return segment.start;
    }
  }
  return segments.at(-1)?.end ?? 0;
}

function sentenceBounds(text) {
  if ('Segmenter' in Intl) {
    const segmenter = new Intl.Segmenter(document.documentElement.lang || undefined, {
      granularity: 'sentence',
    });
    return Array.from(segmenter.segment(text), ({index, segment}) => ({
      start: index,
      end: index + segment.length,
    }));
  }
  const bounds = [];
  const pattern = /[^.!?。！？\\n]+(?:[.!?。！？]+|\\n|$)/gu;
  for (const match of text.matchAll(pattern)) {
    bounds.push({start: match.index, end: match.index + match[0].length});
  }
  return bounds;
}

function trimBounds(text, start, end) {
  while (start < end && /\\s/u.test(text[start])) start += 1;
  while (end > start && /\\s/u.test(text[end - 1])) end -= 1;
  return {start, end};
}

export function snapStartToWordBoundary(text, offset) {
  const safeOffset = Math.max(0, Math.min(offset, text.length));
  if (
    safeOffset === 0
    || safeOffset === text.length
    || !/[\\p{Script=Latin}\\p{Number}_'’]/u.test(text[safeOffset - 1])
    || !/[\\p{Script=Latin}\\p{Number}_'’]/u.test(text[safeOffset])
  ) {
    return safeOffset;
  }
  if ('Segmenter' in Intl) {
    const locale = typeof document === 'undefined'
      ? undefined
      : document.documentElement.lang || undefined;
    const segmenter = new Intl.Segmenter(locale, {granularity: 'word'});
    for (const segment of segmenter.segment(text)) {
      const end = segment.index + segment.segment.length;
      if (segment.isWordLike && segment.index < safeOffset && safeOffset < end) {
        return segment.index;
      }
      if (segment.index >= safeOffset) break;
    }
  }
  let start = safeOffset;
  while (
    start > 0
    && /[\\p{Script=Latin}\\p{Number}_'’]/u.test(text[start - 1])
  ) {
    start -= 1;
  }
  return start;
}

function safeSizedBounds(text, start, end) {
  const chunks = [];
  let cursor = start;
  while (cursor < end) {
    let chunkEnd = Math.min(cursor + MAX_TEXT_CHARACTERS, end);
    if (chunkEnd < end) {
      const candidate = text.slice(cursor, chunkEnd);
      const breakAt = Math.max(candidate.lastIndexOf(' '), candidate.lastIndexOf('\\n'));
      if (breakAt > MAX_TEXT_CHARACTERS / 2) chunkEnd = cursor + breakAt + 1;
    }
    const trimmed = trimBounds(text, cursor, chunkEnd);
    if (trimmed.start < trimmed.end) chunks.push(trimmed);
    cursor = chunkEnd;
  }
  return chunks;
}

function startPoint(segments, offset) {
  for (const segment of segments) {
    if (offset <= segment.end) {
      return {
        node: segment.node,
        offset: Math.max(0, Math.min(offset - segment.start, segment.node.data.length)),
      };
    }
  }
  const last = segments.at(-1);
  return last ? {node: last.node, offset: last.node.data.length} : null;
}

function endPoint(segments, offset) {
  for (let index = segments.length - 1; index >= 0; index -= 1) {
    const segment = segments[index];
    if (offset >= segment.start) {
      return {
        node: segment.node,
        offset: Math.max(0, Math.min(offset - segment.start, segment.node.data.length)),
      };
    }
  }
  const first = segments[0];
  return first ? {node: first.node, offset: 0} : null;
}

function rangeFromBounds(segments, start, end) {
  const from = startPoint(segments, start);
  const to = endPoint(segments, end);
  if (!from || !to) return null;
  const range = document.createRange();
  range.setStart(from.node, from.offset);
  range.setEnd(to.node, to.offset);
  return range.collapsed ? null : range;
}

export function readingQueueFromSelection(selectionRange) {
  const startNode = selectionRange.startContainer;
  const startElement = startNode.nodeType === Node.ELEMENT_NODE
    ? startNode
    : startNode.parentElement;
  const article = startElement?.closest('.theme-doc-markdown');
  if (!article) return [];
  const {text, segments} = readingDocument(article);
  if (!segments.length) return [];
  const selectionOffset = snapStartToWordBoundary(
    text,
    selectionStartOffset(selectionRange, segments),
  );
  const queue = [];
  for (const sentence of sentenceBounds(text)) {
    if (sentence.end <= selectionOffset) continue;
    const start = Math.max(sentence.start, selectionOffset);
    for (const bounds of safeSizedBounds(text, start, sentence.end)) {
      const range = rangeFromBounds(segments, bounds.start, bounds.end);
      const spokenText = range?.toString().replace(/\\s+/gu, ' ').trim();
      if (range && spokenText) queue.push({text: spokenText, range});
    }
  }
  return queue;
}

export function highlightAndCenter(range) {
  if (CSS.highlights && typeof Highlight !== 'undefined') {
    CSS.highlights.set(HIGHLIGHT_NAME, new Highlight(range));
  }
  const rect = range.getBoundingClientRect();
  if (rect.width || rect.height) {
    window.scrollTo({
      top: Math.max(0, window.scrollY + rect.top + rect.height / 2 - window.innerHeight / 2),
      behavior: 'smooth',
    });
  }
}

export function isEditableTarget(target) {
  return target instanceof Element && Boolean(
    target.closest('input, textarea, select, button, [contenteditable="true"], [role="textbox"]'),
  );
}
"""


def _selection_tts_reader_js() -> str:
    return """import React, {useCallback, useEffect, useRef, useState} from 'react';
import {useLocation} from '@docusaurus/router';
import {
  clearReadingHighlight,
  highlightAndCenter,
  isEditableTarget,
  readingQueueFromSelection,
  selectionDetails,
} from './readingQueue';

const SAMPLE_RATE = 24000;
const INITIAL_BUFFER_SECONDS = 0.35;
const MAX_BUFFER_AHEAD_SECONDS = 10;
const BUFFER_CAPACITY_RESERVE_SECONDS = 1;
const REBUFFER_SECONDS = 0.12;
const SENTENCE_CROSSFADE_SECONDS = 0.008;
const START_FADE_SECONDS = 0.006;

function abortError() {
  return new DOMException('朗读已停止', 'AbortError');
}

function abortableDelay(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(abortError());
      return;
    }
    function onAbort() {
      window.clearTimeout(timer);
      reject(abortError());
    }
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, milliseconds);
    signal.addEventListener('abort', onAbort, {once: true});
  });
}

async function waitForBufferCapacity(audioContext, timeline, signal) {
  while (
    timeline.hasAudio
    && timeline.nextStartTime - audioContext.currentTime
      > MAX_BUFFER_AHEAD_SECONDS - BUFFER_CAPACITY_RESERVE_SECONDS
  ) {
    await abortableDelay(50, signal);
  }
}

async function waitUntilAudioTime(audioContext, targetTime, signal) {
  while (audioContext.currentTime + 0.015 < targetTime) {
    const remainingMilliseconds = (targetTime - audioContext.currentTime) * 1000;
    await abortableDelay(Math.min(50, Math.max(10, remainingMilliseconds)), signal);
  }
}

export default function SelectionTtsReader() {
  const location = useLocation();
  const [selection, setSelection] = useState(null);
  const [state, setState] = useState('idle');
  const [message, setMessage] = useState('选择正文文字即可朗读');
  const [speed, setSpeed] = useState(1);
  const audioContextRef = useRef(null);
  const audioSourcesRef = useRef(new Set());
  const abortRef = useRef(null);
  const pendingPlaybackRef = useRef(new Set());
  const requestStartedAtRef = useRef(0);
  const playbackIdRef = useRef(0);
  const speedRef = useRef(1);
  const continuousRef = useRef(false);
  const progressRef = useRef('');
  const pathnameRef = useRef(location.pathname);

  const releaseAudio = useCallback(() => {
    playbackIdRef.current += 1;
    for (const resolve of pendingPlaybackRef.current) resolve();
    pendingPlaybackRef.current.clear();
    for (const source of audioSourcesRef.current) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        // A source that already ended cannot be stopped again.
      }
    }
    audioSourcesRef.current.clear();
    const context = audioContextRef.current;
    audioContextRef.current = null;
    if (context && context.state !== 'closed') void context.close();
    clearReadingHighlight();
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    continuousRef.current = false;
    progressRef.current = '';
    releaseAudio();
    setState('stopped');
    setMessage('已停止');
  }, [releaseAudio]);

  const enqueueStream = useCallback(async (
    text,
    audioContext,
    controller,
    playbackId,
    timeline,
    onStarted,
  ) => {
    const response = await fetch('/api/tts', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text}),
      signal: controller.signal,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `本地语音服务返回 ${response.status}`);
    }
    const payload = await response.json();
    if (
      typeof payload.streamUrl !== 'string'
      || !payload.streamUrl.startsWith('/api/tts/stream/')
    ) {
      throw new Error('本地语音服务返回了无效的流地址。');
    }
    const streamResponse = await fetch(payload.streamUrl, {signal: controller.signal});
    if (!streamResponse.ok || !streamResponse.body) {
      throw new Error(`本地音频流返回 ${streamResponse.status}`);
    }

    const localSources = new Set();
    let resolvePlayback;
    let playbackResolved = false;
    const playbackComplete = new Promise((resolve) => {
      resolvePlayback = resolve;
    });
    function resolvePlaybackOnce() {
      if (playbackResolved) return;
      playbackResolved = true;
      pendingPlaybackRef.current.delete(resolvePlaybackOnce);
      resolvePlayback();
    }
    pendingPlaybackRef.current.add(resolvePlaybackOnce);
    const reader = streamResponse.body.getReader();
    let headerBytesRemaining = 44;
    let leftover = new Uint8Array(0);
    let receivedAudio = false;
    let streamFinished = false;
    let lastSentenceGain = null;
    let lastSentenceEndTime = 0;

    function finishIfReady() {
      if (
        streamFinished
        && localSources.size === 0
        && playbackIdRef.current === playbackId
      ) {
        resolvePlaybackOnce();
      }
    }

    function schedulePcm(pcmBytes) {
      const combined = new Uint8Array(leftover.length + pcmBytes.length);
      combined.set(leftover);
      combined.set(pcmBytes, leftover.length);
      const usableLength = combined.length - (combined.length % 2);
      leftover = combined.slice(usableLength);
      if (!usableLength) return;

      const samples = new Float32Array(usableLength / 2);
      const view = new DataView(combined.buffer, combined.byteOffset, usableLength);
      for (let index = 0; index < samples.length; index += 1) {
        samples[index] = view.getInt16(index * 2, true) / 32768;
      }
      const buffer = audioContext.createBuffer(1, samples.length, SAMPLE_RATE);
      buffer.copyToChannel(samples, 0);
      const source = audioContext.createBufferSource();
      const gainNode = audioContext.createGain();
      const playbackRate = speedRef.current;
      source.buffer = buffer;
      source.playbackRate.value = playbackRate;
      source.connect(gainNode);
      gainNode.connect(audioContext.destination);

      const isFirstSentenceBlock = !receivedAudio;
      let startAt;
      if (!timeline.hasAudio) {
        startAt = audioContext.currentTime + INITIAL_BUFFER_SECONDS;
        gainNode.gain.setValueAtTime(0, startAt);
        gainNode.gain.linearRampToValueAtTime(
          1,
          startAt + Math.min(START_FADE_SECONDS, buffer.duration / playbackRate / 2),
        );
      } else if (
        isFirstSentenceBlock
        && timeline.nextStartTime
          > audioContext.currentTime + SENTENCE_CROSSFADE_SECONDS
      ) {
        startAt = timeline.nextStartTime - SENTENCE_CROSSFADE_SECONDS;
        gainNode.gain.setValueAtTime(0, startAt);
        gainNode.gain.linearRampToValueAtTime(1, timeline.nextStartTime);
      } else if (timeline.nextStartTime < audioContext.currentTime) {
        startAt = audioContext.currentTime + REBUFFER_SECONDS;
        gainNode.gain.setValueAtTime(0, startAt);
        gainNode.gain.linearRampToValueAtTime(
          1,
          startAt + Math.min(START_FADE_SECONDS, buffer.duration / playbackRate / 2),
        );
      } else {
        startAt = timeline.nextStartTime;
      }

      const endAt = startAt + buffer.duration / playbackRate;
      timeline.hasAudio = true;
      timeline.nextStartTime = endAt;
      lastSentenceGain = gainNode;
      lastSentenceEndTime = endAt;
      localSources.add(source);
      audioSourcesRef.current.add(source);
      source.onended = () => {
        localSources.delete(source);
        audioSourcesRef.current.delete(source);
        source.disconnect();
        gainNode.disconnect();
        finishIfReady();
      };
      source.start(startAt);
      if (isFirstSentenceBlock) {
        receivedAudio = true;
        void waitUntilAudioTime(audioContext, startAt, controller.signal)
          .then(() => {
            if (playbackIdRef.current === playbackId) onStarted();
          })
          .catch((error) => {
            if (error.name !== 'AbortError') console.error(error);
          });
      }
    }

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      let audioBytes = value;
      if (headerBytesRemaining) {
        const skipped = Math.min(headerBytesRemaining, audioBytes.length);
        headerBytesRemaining -= skipped;
        audioBytes = audioBytes.slice(skipped);
      }
      if (audioBytes.length) schedulePcm(audioBytes);
    }
    if (!receivedAudio) throw new Error('本地语音服务没有返回音频。');
    if (lastSentenceGain && lastSentenceEndTime > audioContext.currentTime) {
      const fadeDuration = Math.min(
        SENTENCE_CROSSFADE_SECONDS,
        Math.max(0, lastSentenceEndTime - audioContext.currentTime),
      );
      const fadeStart = lastSentenceEndTime - fadeDuration;
      lastSentenceGain.gain.setValueAtTime(1, fadeStart);
      lastSentenceGain.gain.linearRampToValueAtTime(0, lastSentenceEndTime);
    }
    streamFinished = true;
    finishIfReady();
    if (controller.signal.aborted || playbackIdRef.current !== playbackId) {
      throw abortError();
    }
    return {playbackComplete};
  }, []);

  const startReading = useCallback(async (items, continuous) => {
    if (!items.length) {
      setSelection(null);
      setState('error');
      setMessage('无法从此处识别可朗读的正文。');
      return;
    }
    abortRef.current?.abort();
    releaseAudio();
    const controller = new AbortController();
    abortRef.current = controller;
    continuousRef.current = continuous;
    requestStartedAtRef.current = Date.now();
    const playbackId = playbackIdRef.current;
    setSelection(null);
    window.getSelection()?.removeAllRanges();
    setState('loading');
    try {
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      await audioContext.resume();
      const timeline = {hasAudio: false, nextStartTime: 0};
      const playbackPromises = [];
      for (let index = 0; index < items.length; index += 1) {
        if (controller.signal.aborted) throw abortError();
        await waitForBufferCapacity(audioContext, timeline, controller.signal);
        const item = items[index];
        const progress = continuous ? `第 ${index + 1}/${items.length} 句` : '';
        const {playbackComplete} = await enqueueStream(
          item.text,
          audioContext,
          controller,
          playbackId,
          timeline,
          () => {
            if (continuous && item.range) highlightAndCenter(item.range);
            progressRef.current = progress;
            const startupSeconds = (Date.now() - requestStartedAtRef.current) / 1000;
            if (audioContext.state === 'suspended') {
              setState('paused');
              setMessage(`已暂停${progress ? ` · ${progress}` : ''}`);
            } else {
              setState('playing');
              setMessage(
                continuous
                  ? `正在连续朗读 · ${progress}`
                  : `正在流式朗读 · ${startupSeconds.toFixed(1)} 秒启动`,
              );
            }
          },
        );
        playbackPromises.push(playbackComplete);
      }
      await Promise.all(playbackPromises);
      if (controller.signal.aborted || playbackIdRef.current !== playbackId) throw abortError();
      continuousRef.current = false;
      progressRef.current = '';
      setState('stopped');
      setMessage(continuous ? '连续朗读完成' : '朗读完成');
      releaseAudio();
    } catch (error) {
      if (error.name === 'AbortError') return;
      continuousRef.current = false;
      progressRef.current = '';
      setState('error');
      setMessage(error.message || '本地语音生成失败。');
      releaseAudio();
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [enqueueStream, releaseAudio]);

  const speakSelection = useCallback((details) => {
    void startReading([{text: details.text, range: null}], false);
  }, [startReading]);

  const speakContinuously = useCallback((details) => {
    void startReading(readingQueueFromSelection(details.range), true);
  }, [startReading]);

  const togglePause = useCallback(() => {
    const audioContext = audioContextRef.current;
    if (!audioContext) return;
    if (audioContext.state === 'running') {
      audioContext.suspend().then(() => {
        setState('paused');
        setMessage(
          continuousRef.current
            ? `已暂停 · ${progressRef.current} · 空格键继续`
            : '已暂停',
        );
      });
    } else {
      audioContext.resume().then(() => {
        setState('playing');
        setMessage(
          continuousRef.current
            ? `正在连续朗读 · ${progressRef.current}`
            : '正在朗读',
        );
      }).catch(() => {
        setState('error');
        setMessage('浏览器无法继续播放语音。');
      });
    }
  }, []);

  useEffect(() => {
    function updateSelection() {
      if (['loading', 'playing', 'paused'].includes(state)) {
        setSelection(null);
        return;
      }
      window.requestAnimationFrame(() => setSelection(selectionDetails()));
    }
    function keyboardShortcut(event) {
      if (event.altKey && event.key.toLocaleLowerCase() === 'r') {
        const details = selectionDetails();
        if (details) {
          event.preventDefault();
          speakSelection(details);
        }
      }
      if (
        event.code === 'Space'
        && !event.repeat
        && continuousRef.current
        && ['loading', 'playing', 'paused'].includes(state)
        && !isEditableTarget(event.target)
      ) {
        event.preventDefault();
        togglePause();
      }
      if (event.key === 'Escape' && ['loading', 'playing', 'paused'].includes(state)) stop();
    }
    document.addEventListener('mouseup', updateSelection);
    document.addEventListener('keyup', updateSelection);
    document.addEventListener('keydown', keyboardShortcut);
    window.addEventListener('scroll', updateSelection, true);
    window.addEventListener('resize', updateSelection);
    return () => {
      document.removeEventListener('mouseup', updateSelection);
      document.removeEventListener('keyup', updateSelection);
      document.removeEventListener('keydown', keyboardShortcut);
      window.removeEventListener('scroll', updateSelection, true);
      window.removeEventListener('resize', updateSelection);
    };
  }, [speakSelection, state, stop, togglePause]);

  useEffect(() => {
    if (pathnameRef.current !== location.pathname) stop();
    pathnameRef.current = location.pathname;
  }, [location.pathname, stop]);

  useEffect(() => () => {
    abortRef.current?.abort();
    continuousRef.current = false;
    progressRef.current = '';
    releaseAudio();
  }, [releaseAudio]);

  useEffect(() => {
    speedRef.current = speed;
  }, [speed]);

  return (
    <>
      {selection ? (
        <div
          className="booksite-tts-selection"
          role="toolbar"
          aria-label="Qwen3-TTS 朗读选项"
          style={{top: selection.top, left: selection.left}}
          onMouseDown={(event) => event.preventDefault()}
          onMouseUp={(event) => event.stopPropagation()}
        >
          <button
            type="button"
            onClick={() => speakSelection(selection)}
            aria-label="使用 Qwen3-TTS 朗读选中文字"
          >
            <span aria-hidden="true">▶</span> Qwen3 朗读选中
          </button>
          <button
            type="button"
            onClick={() => speakContinuously(selection)}
            aria-label="从选择位置开始连续朗读"
          >
            从此处连续朗读
          </button>
        </div>
      ) : null}
      {state !== 'idle' ? (
        <section className={`booksite-tts-player is-${state}`} aria-label="本地语音朗读器">
          <div>
            <strong>Qwen3-TTS</strong>
            <span role="status" aria-live="polite">{message}</span>
            {continuousRef.current ? <small>空格键：暂停/继续</small> : null}
          </div>
          <label>
            <span className="sr-only">朗读速度</span>
            <select
              value={speed}
              onChange={(event) => setSpeed(Number(event.target.value))}
              aria-label="朗读速度"
            >
              <option value="0.75">0.75×</option>
              <option value="1">1×</option>
              <option value="1.25">1.25×</option>
              <option value="1.5">1.5×</option>
            </select>
          </label>
          {state === 'loading' || state === 'playing' || state === 'paused' ? (
            <button type="button" onClick={togglePause}>
              {state === 'paused' ? '继续' : '暂停'}
            </button>
          ) : null}
          {state === 'loading' || state === 'playing' || state === 'paused' ? (
            <button type="button" onClick={stop}>停止</button>
          ) : (
            <button
              type="button"
              onClick={() => setState('idle')}
              aria-label="关闭朗读器"
            >
              关闭
            </button>
          )}
        </section>
      ) : null}
    </>
  );
}
"""


def _root_js() -> str:
    return """import React from 'react';
import SelectionTtsReader from '@site/src/components/SelectionTtsReader';

export default function Root({children}) {
  return (
    <>
      {children}
      <SelectionTtsReader />
    </>
  );
}
"""


def _config_js(book: BookIR) -> str:
    title = _js_string(book.title)
    return f"""// Generated by booksite. Source patterns:
// https://docusaurus.io/docs/docs-introduction/
// https://docusaurus.io/docs/markdown-features/plugins
import {{themes as prismThemes}} from 'prism-react-renderer';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

/** @type {{import('@docusaurus/types').Config}} */
const config = {{
  title: {title},
  tagline: 'Local PDF book reader',
  favicon: 'favicon.svg',
  url: 'http://localhost',
  baseUrl: '/',
  onBrokenLinks: 'throw',
  markdown: {{hooks: {{onBrokenMarkdownLinks: 'throw'}}}},
  i18n: {{defaultLocale: 'en', locales: ['en']}},
  presets: [[
    'classic',
    {{
      docs: {{
        routeBasePath: '/',
        sidebarPath: './sidebars.js',
        remarkPlugins: [remarkMath],
        rehypePlugins: [rehypeKatex],
      }},
      blog: false,
      theme: {{customCss: './src/css/custom.css'}},
    }},
  ]],
  themeConfig: {{
    colorMode: {{respectPrefersColorScheme: true}},
    navbar: {{
      title: 'Booksite',
      items: [
        {{to: '/', label: {title}, position: 'left', className: 'booksite-book-title'}},
        {{type: 'docSidebar', sidebarId: 'bookSidebar', label: 'Read', position: 'left'}},
        {{to: '/quality-report', label: 'Quality report', position: 'left'}},
        {{
          to: '/search',
          label: 'Search this book',
          position: 'right',
          className: 'booksite-search-link',
        }},
      ],
    }},
    docs: {{sidebar: {{hideable: true, autoCollapseCategories: false}}}},
    prism: {{theme: prismThemes.github, darkTheme: prismThemes.dracula}},
  }},
}};

export default config;
"""


def _search_page_js() -> str:
    return """import React, {useEffect, useMemo, useState} from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';

export default function SearchPage() {
  const [entries, setEntries] = useState([]);
  const [query, setQuery] = useState('');
  const [loadError, setLoadError] = useState(false);
  const indexUrl = useBaseUrl('/search-index.json');

  useEffect(() => {
    fetch(indexUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`Search index: ${response.status}`);
        return response.json();
      })
      .then((data) => {
        setEntries(data);
        setLoadError(false);
      })
      .catch(() => {
        setEntries([]);
        setLoadError(true);
      });
  }, [indexUrl]);

  const results = useMemo(() => {
    const terms = query.toLocaleLowerCase().trim().split(/\\s+/).filter(Boolean);
    if (!terms.length) return entries.slice(0, 12);
    return entries.filter((entry) => {
      const haystack = `${entry.title} ${entry.text}`.toLocaleLowerCase();
      return terms.every((term) => haystack.includes(term));
    }).slice(0, 40);
  }, [entries, query]);

  return (
    <Layout title="Search" description="Search this converted book locally">
      <main className="booksite-search-page">
        <p className="booksite-eyebrow">LOCAL BOOK INDEX</p>
        <h1>Search this book</h1>
        <label className="booksite-search-field">
          <span className="sr-only">Search terms</span>
          <input
            autoFocus
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search chapters and text…"
          />
        </label>
        <p className="booksite-search-count" role="status" aria-live="polite">
          {loadError
            ? 'Search index could not be loaded.'
            : query
              ? `${results.length} matching sections`
              : 'Browse indexed sections'}
        </p>
        <ol className="booksite-search-results">
          {results.map((entry) => (
            <li key={entry.url}>
              <Link to={entry.url}><h2>{entry.title}</h2></Link>
              <p>{entry.text.slice(0, 240)}{entry.text.length > 240 ? '…' : ''}</p>
              <small>PDF pages {entry.pages[0]}–{entry.pages.at(-1)}</small>
            </li>
          ))}
        </ol>
      </main>
    </Layout>
  );
}
"""


def _quality_page_js(book: BookIR) -> str:
    pages = [
        {
            "page": page.page_index + 1,
            "engine": page.selected_engine,
            "score": page.quality_score,
            "chars": page.native_text_char_count,
            "reasons": page.fallback_reasons,
        }
        for page in book.pages
    ]
    average_quality = (
        sum(page.quality_score for page in book.pages) / len(book.pages) if book.pages else 0
    )
    report = {
        "title": book.title or "Converted book",
        "metrics": [
            {"label": "pages", "value": book.page_count},
            {"label": "sections", "value": len(book.sections)},
            {"label": "assets", "value": len(book.assets)},
            {
                "label": "review pages",
                "value": sum(bool(page.fallback_reasons) for page in book.pages),
            },
            {"label": "avg quality", "value": round(average_quality, 4)},
        ],
        "pages": pages,
    }
    payload = json.dumps(report, ensure_ascii=True, separators=(",", ":"))
    return f"""import React from 'react';
import Layout from '@theme/Layout';

const report = {payload};

export default function QualityReportPage() {{
  return (
    <Layout title="Quality report" description="Local PDF conversion quality report">
      <main className="booksite-report-page">
        <p className="booksite-eyebrow">CONVERSION AUDIT</p>
        <h1>Quality report</h1>
        <p className="booksite-report-subtitle">
          {{report.title}} · local native-text pipeline
        </p>
        <section className="booksite-metrics">
          {{report.metrics.map((metric) => (
            <div key={{metric.label}}>
              <strong>{{metric.value}}</strong>
              <span>{{metric.label}}</span>
            </div>
          ))}}
        </section>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Page</th><th>Engine</th><th>Score</th>
                <th>Chars</th><th>Review reason</th>
              </tr>
            </thead>
            <tbody>
              {{report.pages.map((page) => (
                <tr key={{page.page}}>
                  <td>{{page.page}}</td>
                  <td>{{page.engine}}</td>
                  <td>{{page.score.toFixed(2)}}</td>
                  <td>{{page.chars}}</td>
                  <td>{{page.reasons.join(', ') || '—'}}</td>
                </tr>
              ))}}
            </tbody>
          </table>
        </div>
      </main>
    </Layout>
  );
}}
"""


def _custom_css() -> str:
    return """@import 'katex/dist/katex.min.css';

:root {
  --ifm-color-primary: #1463ff;
  --ifm-color-primary-dark: #0052ef;
  --ifm-color-primary-darker: #004de1;
  --ifm-color-primary-darkest: #003fb9;
  --ifm-color-primary-light: #3277ff;
  --ifm-color-primary-lighter: #4180ff;
  --ifm-color-primary-lightest: #6f9fff;
  --ifm-background-color: #ffffff;
  --ifm-font-family-base: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  --ifm-heading-font-family: Georgia, "Times New Roman", serif;
  --ifm-font-color-base: #121826;
  --ifm-line-height-base: 1.72;
  --doc-sidebar-width: 285px;
  --booksite-border: #dfe4ea;
  --booksite-muted: #5f6b7a;
  --booksite-surface: #f6f8fb;
}

.navbar {
  border-bottom: 1px solid var(--booksite-border);
  box-shadow: none;
}

.navbar__brand { color: #1463ff; font-weight: 760; }
.navbar__title { font-size: 1.25rem; }
.booksite-book-title {
  max-width: 22rem;
  margin-left: 0.4rem;
  padding-left: 1.25rem;
  border-left: 1px solid var(--booksite-border);
  overflow: hidden;
  color: var(--ifm-font-color-base);
  font-weight: 680;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.booksite-search-link {
  min-width: 10rem;
  border: 1px solid var(--booksite-border);
  border-radius: 6px;
  color: var(--booksite-muted);
}
.booksite-search-link::before { content: "⌕"; margin-right: 0.5rem; }
.theme-doc-sidebar-container { border-right-color: var(--booksite-border) !important; }
.menu__link { border-radius: 6px; line-height: 1.45; }
.menu__link--active { border-left: 3px solid #1463ff; background: #f1f5ff; }

.theme-doc-markdown {
  max-width: 900px;
  padding-left: 32px;
  border-left: 2px solid #d8e4ff;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.08rem;
}

.theme-doc-markdown h1 { font-size: clamp(2.2rem, 4vw, 3.4rem); letter-spacing: -0.035em; }
.theme-doc-markdown h2 { margin-top: 2.25rem; }
.theme-doc-markdown em:last-child {
  color: var(--booksite-muted);
  font-family: var(--ifm-font-family-base);
  font-size: 0.84rem;
}

pre, code, .table-wrapper { max-width: 100%; overflow-x: auto; }
pre { border: 1px solid var(--booksite-border); border-radius: 6px; box-shadow: none; }
.booksite-pdf-code {
  position: relative;
  max-width: 100%;
  margin: 1.2rem 0;
  overflow: hidden;
  border-left: 4px solid var(--pdf-code-border);
  border-radius: 0;
  background: var(--pdf-code-background);
  font-family: Consolas, "SFMono-Regular", Menlo, monospace;
}
.booksite-pdf-code pre {
  max-width: 100%;
  margin: 0;
  padding: 0.7rem 1rem 0.8rem 1.25rem;
  overflow-x: auto;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  color: inherit;
  font-family: inherit;
  font-size: var(--pdf-code-font-size);
  line-height: 1.62;
  tab-size: 4;
}
.booksite-pdf-code code {
  display: block;
  min-width: max-content;
  padding: 0;
  overflow: visible;
  background: transparent;
  color: inherit;
  font: inherit;
  white-space: pre;
}
.booksite-pdf-code button {
  position: absolute;
  z-index: 1;
  top: 0.45rem;
  right: 0.55rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid rgb(18 24 38 / 22%);
  border-radius: 4px;
  opacity: 0;
  background: rgb(255 255 255 / 92%);
  color: #121826;
  font-family: var(--ifm-font-family-base);
  font-size: 0.7rem;
  cursor: pointer;
  transition: opacity 120ms ease;
}
.booksite-pdf-code:hover button,
.booksite-pdf-code button:focus-visible { opacity: 1; }
.booksite-pdf-url-callout {
  max-width: 100%;
  margin: 1.2rem 0;
  padding: 0.85rem 1.25rem;
  border-left: 4px solid var(--pdf-callout-border);
  background: var(--pdf-callout-background);
  color: inherit;
  font: inherit;
  line-height: 1.72;
}
.booksite-pdf-url-callout a {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 0.15em;
}
.booksite-pdf-url-callout code {
  padding: 0;
  background: transparent;
  color: inherit;
  font-family: Consolas, "SFMono-Regular", Menlo, monospace;
  font-size: 0.92em;
  white-space: normal;
  overflow-wrap: anywhere;
}
table { display: table; width: 100%; }
table thead { position: sticky; top: var(--ifm-navbar-height); z-index: 1; }
table th { background: var(--booksite-surface); }
img { display: block; max-width: 100%; height: auto; margin-inline: auto; }
.table-of-contents { font-size: 0.82rem; }
.table-of-contents::before {
  content: "On this page";
  display: block;
  margin-bottom: 0.75rem;
  color: var(--ifm-font-color-base);
  font-size: 0.9rem;
  font-weight: 720;
}

.booksite-search-page {
  width: min(840px, calc(100% - 40px));
  margin: 0 auto;
  padding: 72px 0 96px;
}
.booksite-eyebrow {
  margin: 0 0 0.75rem;
  color: var(--ifm-color-primary);
  font-size: 0.75rem;
  font-weight: 750;
  letter-spacing: 0.12em;
}
.booksite-search-page h1 {
  margin-bottom: 1.75rem;
  font-family: var(--ifm-heading-font-family);
  font-size: clamp(2.5rem, 7vw, 4.5rem);
}
.booksite-search-field input {
  width: 100%;
  padding: 0.9rem 1rem;
  border: 1px solid var(--booksite-border);
  border-radius: 7px;
  background: var(--ifm-background-color);
  color: var(--ifm-font-color-base);
  font: inherit;
}
.booksite-search-field input:focus {
  border-color: var(--ifm-color-primary);
  box-shadow: 0 0 0 3px rgb(20 99 255 / 14%);
  outline: none;
}
.booksite-search-count { margin: 0.8rem 0 1.5rem; color: var(--booksite-muted); }
.booksite-search-results { padding: 0; list-style: none; }
.booksite-search-results li {
  padding: 1.3rem 0;
  border-top: 1px solid var(--booksite-border);
}
.booksite-search-results h2 { margin: 0 0 0.35rem; font-size: 1.3rem; }
.booksite-search-results p { margin: 0 0 0.35rem; color: var(--booksite-muted); }
.booksite-search-results small { color: var(--booksite-muted); }

.booksite-report-page {
  width: min(1080px, calc(100% - 40px));
  margin: 0 auto;
  padding: 72px 0 96px;
}
.booksite-report-page h1 {
  margin-bottom: 0.4rem;
  font-family: var(--ifm-heading-font-family);
  font-size: clamp(2.5rem, 7vw, 4.5rem);
}
.booksite-report-subtitle { color: var(--booksite-muted); }
.booksite-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  gap: 1px;
  margin: 2rem 0;
  border: 1px solid var(--booksite-border);
  background: var(--booksite-border);
}
.booksite-metrics div { padding: 1.25rem; background: var(--ifm-background-color); }
.booksite-metrics strong { display: block; font-size: 1.5rem; }
.booksite-metrics span { color: var(--booksite-muted); }

.booksite-tts-selection {
  position: fixed;
  z-index: 1000;
  display: flex;
  overflow: hidden;
  border: 1px solid #0e4ed8;
  border-radius: 999px;
  box-shadow: 0 8px 24px rgb(18 24 38 / 22%);
  background: #1463ff;
  font-family: var(--ifm-font-family-base);
}
.booksite-tts-selection button {
  padding: 0.5rem 0.72rem;
  border: 0;
  background: transparent;
  color: #fff;
  font: inherit;
  font-size: 0.76rem;
  font-weight: 680;
  line-height: 1;
  cursor: pointer;
}
.booksite-tts-selection button + button { border-left: 1px solid rgb(255 255 255 / 35%); }
.booksite-tts-selection button:hover { background: #0052ef; }
.booksite-tts-selection button:focus-visible {
  outline: 3px solid rgb(20 99 255 / 30%);
  outline-offset: -3px;
}
::highlight(booksite-tts-current) {
  background: rgb(255 203 71 / 70%);
  color: inherit;
  text-decoration: underline #1463ff 2px;
  text-underline-offset: 0.16em;
}
.booksite-tts-player {
  position: fixed;
  z-index: 999;
  right: 22px;
  bottom: 22px;
  display: flex;
  align-items: center;
  gap: 0.65rem;
  max-width: min(620px, calc(100vw - 32px));
  padding: 0.75rem 0.85rem;
  border: 1px solid var(--booksite-border);
  border-left: 4px solid #1463ff;
  border-radius: 8px;
  box-shadow: 0 12px 36px rgb(18 24 38 / 18%);
  background: var(--ifm-background-color);
  color: var(--ifm-font-color-base);
  font-family: var(--ifm-font-family-base);
}
.booksite-tts-player > div {
  display: grid;
  min-width: 11rem;
  line-height: 1.25;
}
.booksite-tts-player > div span {
  margin-top: 0.16rem;
  color: var(--booksite-muted);
  font-size: 0.76rem;
}
.booksite-tts-player > div small {
  margin-top: 0.2rem;
  color: var(--booksite-muted);
  font-size: 0.68rem;
}
.booksite-tts-player select,
.booksite-tts-player button {
  min-height: 2rem;
  padding: 0.32rem 0.55rem;
  border: 1px solid var(--booksite-border);
  border-radius: 5px;
  background: var(--ifm-background-color);
  color: var(--ifm-font-color-base);
  font-family: var(--ifm-font-family-base);
  font-size: 0.78rem;
  font-weight: 650;
  line-height: 1;
}
.booksite-tts-player button { cursor: pointer; }
.booksite-tts-player button:hover { border-color: #1463ff; color: #1463ff; }
.booksite-tts-player.is-loading { border-left-color: #d48a00; }
.booksite-tts-player.is-error { border-left-color: #c83232; }

@media (max-width: 996px) {
  .theme-doc-markdown {
    padding-left: 0;
    border-left: 0;
    font-size: 1rem;
  }
  .main-wrapper main { padding-inline: 20px; }
  .booksite-search-link { min-width: auto; border: 0; }
  .booksite-book-title { max-width: none; border-left: 0; }
  .booksite-pdf-code button { opacity: 1; }
  .booksite-tts-player {
    right: 16px;
    bottom: 16px;
    left: 16px;
    flex-wrap: wrap;
    max-width: none;
  }
  .booksite-tts-player > div { flex: 1 1 100%; }
}
"""


def generate_docusaurus_site(book: BookIR, site_dir: str | Path) -> SiteGenerationResult:
    target = Path(site_dir)
    docs_dir = target / "docs"
    css_dir = target / "src" / "css"
    components_dir = target / "src" / "components"
    pages_dir = target / "src" / "pages"
    theme_dir = target / "src" / "theme"
    static_dir = target / "static"
    docs_dir.mkdir(parents=True, exist_ok=True)
    css_dir.mkdir(parents=True, exist_ok=True)
    components_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    theme_dir.mkdir(parents=True, exist_ok=True)
    static_dir.mkdir(parents=True, exist_ok=True)

    for old_doc in docs_dir.glob("*.md"):
        old_doc.unlink()

    document_paths = []
    for index, section in enumerate(book.sections):
        safe_slug = re.sub(r"[^a-z0-9-]+", "-", section.slug.casefold()).strip("-")
        document_path = docs_dir / f"{section.order:02d}-{safe_slug}.md"
        document_path.write_text(
            _frontmatter(book, index) + "\n" + section.markdown,
            encoding="utf-8",
        )
        document_paths.append(document_path)

    (target / "package.json").write_text(_package_json(), encoding="utf-8")
    cleanup_build = target / "cleanup-build.py"
    cleanup_build.write_text(_cleanup_build_py(), encoding="utf-8")
    cleanup_build.chmod(0o755)
    stale_config = target / "docusaurus.config.js"
    if stale_config.exists():
        stale_config.unlink()
    (target / "docusaurus.config.mjs").write_text(_config_js(book), encoding="utf-8")
    (target / "sidebars.js").write_text(
        "export default {bookSidebar: [{type: 'autogenerated', dirName: '.'}]};\n",
        encoding="utf-8",
    )
    (target / "pnpm-workspace.yaml").write_text(
        "autoInstallPeers: false\nallowBuilds:\n  '@swc/core': true\n  core-js: true\n",
        encoding="utf-8",
    )
    preview_server = target / "serve-local.py"
    preview_server.write_text(_preview_server_py(), encoding="utf-8")
    preview_launcher = target / "打开网站.command"
    preview_launcher.write_text(_preview_launcher_sh(), encoding="utf-8")
    preview_launcher.chmod(0o755)
    (target / "本地打开说明.txt").write_text(
        _preview_guide_text(),
        encoding="utf-8",
    )
    (pages_dir / "search.js").write_text(_search_page_js(), encoding="utf-8")
    (pages_dir / "quality-report.js").write_text(
        _quality_page_js(book),
        encoding="utf-8",
    )
    (components_dir / "PdfCodeBlock.js").write_text(
        _pdf_code_block_js(),
        encoding="utf-8",
    )
    (components_dir / "PdfUrlCallout.js").write_text(
        _pdf_url_callout_js(),
        encoding="utf-8",
    )
    (components_dir / "readingQueue.js").write_text(
        _reading_queue_js(),
        encoding="utf-8",
    )
    (components_dir / "SelectionTtsReader.js").write_text(
        _selection_tts_reader_js(),
        encoding="utf-8",
    )
    (theme_dir / "MDXComponents.js").write_text(
        _mdx_components_js(),
        encoding="utf-8",
    )
    (theme_dir / "Root.js").write_text(
        _root_js(),
        encoding="utf-8",
    )
    (static_dir / "search-index.json").write_text(
        _search_index_json(book),
        encoding="utf-8",
    )
    (static_dir / "favicon.svg").write_text(
        (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            '<rect width="64" height="64" rx="14" fill="#2457d6"/>'
            '<path d="M17 15h24a7 7 0 0 1 7 7v27H24a7 7 0 0 0-7 7z" fill="#fff"/>'
            '<path d="M24 22h17v5H24zm0 10h17v5H24z" fill="#2457d6"/>'
            "</svg>\n"
        ),
        encoding="utf-8",
    )
    (css_dir / "custom.css").write_text(_custom_css(), encoding="utf-8")
    return SiteGenerationResult(target, docs_dir, tuple(document_paths))
