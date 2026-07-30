(() => {
  'use strict';

  const HIGHLIGHT_NAME = 'qwen3-tts-extension-current';
  const BLOCK_SELECTOR = [
    'p',
    'li',
    'h1',
    'h2',
    'h3',
    'h4',
    'h5',
    'h6',
    'pre',
    'blockquote',
    'td',
    'th',
    'figcaption',
  ].join(', ');
  const SKIPPED_SELECTOR = [
    'script',
    'style',
    'noscript',
    'template',
    'svg',
    'nav',
    'aside',
    'footer',
    'button',
    'input',
    'textarea',
    'select',
    'option',
    '[hidden]',
    '[aria-hidden="true"]',
    '[contenteditable="true"]',
  ].join(', ');

  function selectionDetails() {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
    const text = selection.toString().replace(/\s+/gu, ' ').trim();
    if (!text || text.length > QwenReadingQueue.MAX_TEXT_CHARACTERS) return null;
    const range = selection.getRangeAt(0);
    const element = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
      ? range.commonAncestorContainer
      : range.commonAncestorContainer.parentElement;
    if (!element || element.closest(SKIPPED_SELECTOR)) return null;
    const rect = range.getBoundingClientRect();
    if (!rect.width && !rect.height) return null;
    return {text, range: range.cloneRange(), rect};
  }

  function readingRoot(range) {
    const node = range.startContainer;
    const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    return element?.closest('article, main, [role="main"]') || document.body;
  }

  function readableTextNodes(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const parent = node.parentElement;
        if (
          !node.data.trim()
          || !parent
          || parent.closest(SKIPPED_SELECTOR)
          || parent.closest('#qwen3-tts-extension-root')
        ) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    return nodes;
  }

  function readingDocument(root) {
    const segments = [];
    let text = '';
    let previousBlock = null;
    for (const node of readableTextNodes(root)) {
      const block = node.parentElement?.closest(BLOCK_SELECTOR);
      if (text) {
        if (block !== previousBlock) text += '\n';
        else if (!/\s$/u.test(text) && !/^\s/u.test(node.data)) text += ' ';
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
    if (exact) return exact.start + Math.min(range.startOffset, exact.node.data.length);
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

  function readingQueueFromSelection(selectionRange) {
    const {text, segments} = readingDocument(readingRoot(selectionRange));
    if (!segments.length) return [];
    const bounds = QwenReadingQueue.segmentText(
      text,
      selectionStartOffset(selectionRange, segments),
    );
    return bounds.flatMap((item) => {
      const range = rangeFromBounds(segments, item.start, item.end);
      return range ? [{text: item.text, range}] : [];
    });
  }

  function clearHighlight(fallbackLayer) {
    CSS.highlights?.delete(HIGHLIGHT_NAME);
    fallbackLayer?.replaceChildren();
  }

  function renderFallback(range, fallbackLayer) {
    fallbackLayer.replaceChildren();
    for (const rect of range.getClientRects()) {
      if (!rect.width || !rect.height) continue;
      const marker = document.createElement('span');
      marker.className = 'qwen3-tts-fallback-highlight';
      marker.style.left = `${rect.left}px`;
      marker.style.top = `${rect.top}px`;
      marker.style.width = `${rect.width}px`;
      marker.style.height = `${rect.height}px`;
      fallbackLayer.append(marker);
    }
  }

  function renderHighlight(range, fallbackLayer) {
    if (CSS.highlights && typeof Highlight !== 'undefined') {
      CSS.highlights.set(HIGHLIGHT_NAME, new Highlight(range));
      fallbackLayer.replaceChildren();
    } else {
      renderFallback(range, fallbackLayer);
    }
  }

  function highlightAndCenter(range, fallbackLayer) {
    renderHighlight(range, fallbackLayer);
    const rect = range.getBoundingClientRect();
    if (rect.width || rect.height) {
      window.scrollTo({
        top: Math.max(0, window.scrollY + rect.top + rect.height / 2 - innerHeight / 2),
        behavior: 'smooth',
      });
    }
  }

  function isEditableTarget(target) {
    return target instanceof Element && Boolean(
      target.closest(
        'input, textarea, select, button, [contenteditable="true"], [role="textbox"]',
      ),
    );
  }

  globalThis.QwenPageReader = Object.freeze({
    clearHighlight,
    highlightAndCenter,
    isEditableTarget,
    readingQueueFromSelection,
    renderHighlight,
    selectionDetails,
  });
})();
