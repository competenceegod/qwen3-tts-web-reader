(() => {
  'use strict';

  const MAX_TEXT_CHARACTERS = 2000;
  const MAX_QUEUE_ITEMS = 1000;
  const MAX_QUEUE_CHARACTERS = 200000;
  const WORD_CHARACTER = /[\p{Script=Latin}\p{Number}_'’]/u;

  function snapStartToWordBoundary(text, offset) {
    const safeOffset = Math.max(0, Math.min(offset, text.length));
    if (
      safeOffset === 0
      || safeOffset === text.length
      || !WORD_CHARACTER.test(text[safeOffset - 1])
      || !WORD_CHARACTER.test(text[safeOffset])
    ) {
      return safeOffset;
    }
    if ('Segmenter' in Intl) {
      const segmenter = new Intl.Segmenter(undefined, {granularity: 'word'});
      for (const segment of segmenter.segment(text)) {
        const end = segment.index + segment.segment.length;
        if (segment.isWordLike && segment.index < safeOffset && safeOffset < end) {
          return segment.index;
        }
        if (segment.index >= safeOffset) break;
      }
    }
    let start = safeOffset;
    while (start > 0 && WORD_CHARACTER.test(text[start - 1])) start -= 1;
    return start;
  }

  function sentenceBounds(text) {
    if ('Segmenter' in Intl) {
      const segmenter = new Intl.Segmenter(undefined, {granularity: 'sentence'});
      return Array.from(segmenter.segment(text), ({index, segment}) => ({
        start: index,
        end: index + segment.length,
      }));
    }
    const bounds = [];
    const pattern = /[^.!?。！？\n]+(?:[.!?。！？]+|\n|$)/gu;
    for (const match of text.matchAll(pattern)) {
      bounds.push({start: match.index, end: match.index + match[0].length});
    }
    return bounds;
  }

  function trimBounds(text, start, end) {
    while (start < end && /\s/u.test(text[start])) start += 1;
    while (end > start && /\s/u.test(text[end - 1])) end -= 1;
    return {start, end};
  }

  function safeSizedBounds(text, start, end) {
    const chunks = [];
    let cursor = start;
    while (cursor < end) {
      let chunkEnd = Math.min(cursor + MAX_TEXT_CHARACTERS, end);
      if (chunkEnd < end) {
        const candidate = text.slice(cursor, chunkEnd);
        const breakAt = Math.max(candidate.lastIndexOf(' '), candidate.lastIndexOf('\n'));
        if (breakAt > MAX_TEXT_CHARACTERS / 2) chunkEnd = cursor + breakAt + 1;
      }
      const trimmed = trimBounds(text, cursor, chunkEnd);
      if (trimmed.start < trimmed.end) chunks.push(trimmed);
      cursor = chunkEnd;
    }
    return chunks;
  }

  function segmentText(text, selectionOffset = 0) {
    const startOffset = snapStartToWordBoundary(text, selectionOffset);
    const items = [];
    let totalCharacters = 0;
    for (const sentence of sentenceBounds(text)) {
      if (sentence.end <= startOffset) continue;
      const sentenceStart = Math.max(sentence.start, startOffset);
      for (const bounds of safeSizedBounds(text, sentenceStart, sentence.end)) {
        const spokenText = text.slice(bounds.start, bounds.end).replace(/\s+/gu, ' ').trim();
        if (!spokenText) continue;
        if (
          items.length >= MAX_QUEUE_ITEMS
          || totalCharacters + spokenText.length > MAX_QUEUE_CHARACTERS
        ) {
          return items;
        }
        items.push({text: spokenText, start: bounds.start, end: bounds.end});
        totalCharacters += spokenText.length;
      }
    }
    return items;
  }

  globalThis.QwenReadingQueue = Object.freeze({
    MAX_QUEUE_CHARACTERS,
    MAX_QUEUE_ITEMS,
    MAX_TEXT_CHARACTERS,
    segmentText,
    snapStartToWordBoundary,
  });
})();
