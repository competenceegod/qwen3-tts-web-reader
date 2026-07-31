const OFFSCREEN_URL = 'offscreen.html';
const CONTROL_TYPES = new Set([
  'PAUSE_READING',
  'RESUME_READING',
  'SET_SPEED',
  'START_READING',
  'STOP_READING',
]);
const EVENT_TYPES = new Set([
  'READING_ERROR',
  'READING_FINISHED',
  'SENTENCE_STARTED',
  'STATE_CHANGED',
]);
const ALLOWED_SPEEDS = new Set([0.75, 1, 1.25, 1.5]);
const SESSION_ID = /^[A-Za-z0-9_-]{8,80}$/u;
const MAX_ITEMS = 1000;
const MAX_ITEM_CHARACTERS = 2000;
const MAX_TOTAL_CHARACTERS = 200000;
let creatingOffscreen = null;

async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) return;
  creatingOffscreen ??= chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: ['AUDIO_PLAYBACK'],
    justification: 'Stream local Qwen3-TTS audio selected by the user.',
  }).finally(() => {
    creatingOffscreen = null;
  });
  await creatingOffscreen;
}

function validSessionId(value) {
  return typeof value === 'string' && SESSION_ID.test(value);
}

function validPlaybackRequest(message, {recovery = false} = {}) {
  if (
    !Array.isArray(message.items)
    || !ALLOWED_SPEEDS.has(message.speed)
    || typeof message.continuous !== 'boolean'
  ) {
    return false;
  }
  if (
    recovery
    && (
      !Number.isInteger(message.indexOffset)
      || message.indexOffset < 0
      || message.indexOffset >= MAX_ITEMS
    )
  ) {
    return false;
  }
  if (message.items.length === 0 || message.items.length > MAX_ITEMS) return false;
  if (recovery && message.indexOffset + message.items.length > MAX_ITEMS) return false;
  let total = 0;
  for (const item of message.items) {
    if (
      !item
      || typeof item.text !== 'string'
      || item.text.length === 0
      || item.text.length > MAX_ITEM_CHARACTERS
    ) {
      return false;
    }
    total += item.text.length;
    if (total > MAX_TOTAL_CHARACTERS) return false;
  }
  return true;
}

function validControl(message) {
  if (!message || message.target !== 'background') return false;
  if (!CONTROL_TYPES.has(message.type) || !validSessionId(message.sessionId)) return false;
  if (message.type === 'START_READING') return validPlaybackRequest(message);
  if (message.type === 'RESUME_READING') {
    return validPlaybackRequest(message, {recovery: true});
  }
  if (message.type === 'SET_SPEED') return ALLOWED_SPEEDS.has(message.speed);
  return true;
}

function validEvent(message) {
  return Boolean(
    message
    && message.target === 'background'
    && message.type === 'READING_EVENT'
    && EVENT_TYPES.has(message.event)
    && validSessionId(message.sessionId)
    && Number.isInteger(message.tabId)
    && message.tabId >= 0,
  );
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (
    validEvent(message)
    && sender.id === chrome.runtime.id
    && sender.url === chrome.runtime.getURL(OFFSCREEN_URL)
    && !sender.tab
  ) {
    void chrome.tabs.sendMessage(message.tabId, {
      ...message,
      target: 'content',
    }).catch(() => {});
    return false;
  }
  if (!validControl(message) || !Number.isInteger(sender.tab?.id)) return false;
  void ensureOffscreen()
    .then(() => chrome.runtime.sendMessage({
      ...message,
      target: 'offscreen',
      tabId: sender.tab.id,
    }))
    .then(() => sendResponse({ok: true}))
    .catch(() => sendResponse({
      ok: false,
      error: '无法启动扩展音频环境。',
    }));
  return true;
});
