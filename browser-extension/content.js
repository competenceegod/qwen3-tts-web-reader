(() => {
  'use strict';

  if (document.getElementById('qwen3-tts-extension-root')) return;

  const ACTIVE_STATES = new Set(['loading', 'playing', 'paused']);
  const ALLOWED_SPEEDS = new Set([0.75, 1, 1.25, 1.5]);
  const host = document.createElement('div');
  host.id = 'qwen3-tts-extension-root';
  const shadow = host.attachShadow({mode: 'open'});
  const style = document.createElement('style');
  style.textContent = `
    :host { all: initial; color-scheme: light dark; }
    * { box-sizing: border-box; }
    button, select { font: inherit; }
    button {
      min-height: 32px;
      border: 1px solid #c8ccd2;
      border-radius: 6px;
      color: #172033;
      background: #fff;
      padding: 5px 10px;
      cursor: pointer;
    }
    button:hover { background: #f1f4f8; }
    button:focus-visible, select:focus-visible {
      outline: 2px solid #1769d2;
      outline-offset: 2px;
    }
    .selection {
      position: fixed;
      display: none;
      gap: 6px;
      max-width: min(360px, calc(100vw - 24px));
      padding: 6px;
      border: 1px solid #cbd2dc;
      border-radius: 8px;
      background: #f8fafc;
      box-shadow: 0 6px 20px rgb(24 33 48 / 22%);
      pointer-events: auto;
    }
    .selection.visible { display: flex; }
    .selection button:first-child {
      color: #fff;
      border-color: #1769d2;
      background: #1769d2;
    }
    .selection button:first-child:hover { background: #1259b4; }
    .player {
      position: fixed;
      right: 18px;
      bottom: 18px;
      display: none;
      grid-template-columns: minmax(180px, 1fr) auto auto auto;
      align-items: center;
      gap: 8px;
      width: min(620px, calc(100vw - 36px));
      padding: 10px 12px;
      border: 1px solid #cbd2dc;
      border-left: 4px solid #1769d2;
      border-radius: 8px;
      color: #172033;
      background: #fff;
      box-shadow: 0 8px 28px rgb(24 33 48 / 20%);
      pointer-events: auto;
      font: 14px/1.35 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .player.visible { display: grid; }
    .identity { min-width: 0; }
    .identity strong, .identity span, .identity small { display: block; }
    .identity strong { font-size: 14px; }
    .identity span {
      overflow: hidden;
      color: #455167;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .identity small { color: #69758a; }
    label { display: flex; align-items: center; gap: 5px; color: #455167; }
    select {
      min-height: 32px;
      border: 1px solid #c8ccd2;
      border-radius: 6px;
      color: #172033;
      background: #fff;
      padding: 4px 7px;
    }
    .fallback-layer {
      position: fixed;
      inset: 0;
      overflow: hidden;
      pointer-events: none;
    }
    .qwen3-tts-fallback-highlight {
      position: fixed;
      border-bottom: 2px solid #ad7300;
      background: rgb(255 204 51 / 48%);
    }
    @media (max-width: 640px) {
      .player {
        right: 8px;
        bottom: 8px;
        grid-template-columns: 1fr auto auto;
        width: calc(100vw - 16px);
      }
      .player label { grid-column: 1 / -1; grid-row: 2; justify-self: start; }
    }
    @media (prefers-color-scheme: dark) {
      button, select, .player { color: #eef2f8; background: #202633; border-color: #566174; }
      button:hover { background: #30394a; }
      .selection { background: #202633; border-color: #566174; }
      .identity span, label { color: #c6cfdd; }
      .identity small { color: #a8b3c4; }
    }
  `;

  const fallbackLayer = document.createElement('div');
  fallbackLayer.className = 'fallback-layer';
  const selectionBar = document.createElement('div');
  selectionBar.className = 'selection';
  selectionBar.setAttribute('role', 'toolbar');
  selectionBar.setAttribute('aria-label', 'Qwen3-TTS 朗读选项');
  const readSelectedButton = makeButton('▶ 朗读选中', '使用 Qwen3-TTS 朗读选中文字');
  const readContinuousButton = makeButton('从此处连续朗读', '从选择位置开始连续朗读');
  selectionBar.append(readSelectedButton, readContinuousButton);

  const player = document.createElement('section');
  player.className = 'player';
  player.setAttribute('aria-label', 'Qwen3-TTS 本地语音朗读器');
  const identity = document.createElement('div');
  identity.className = 'identity';
  const title = document.createElement('strong');
  title.textContent = 'Qwen3-TTS';
  const status = document.createElement('span');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const shortcut = document.createElement('small');
  shortcut.textContent = 'Space：暂停/继续 · Esc：停止';
  identity.append(title, status, shortcut);
  const speedLabel = document.createElement('label');
  const speedText = document.createElement('span');
  speedText.textContent = '速度';
  const speedSelect = document.createElement('select');
  speedSelect.setAttribute('aria-label', '朗读速度');
  for (const value of ALLOWED_SPEEDS) {
    const option = document.createElement('option');
    option.value = String(value);
    option.textContent = `${value}×`;
    if (value === 1) option.selected = true;
    speedSelect.append(option);
  }
  speedLabel.append(speedText, speedSelect);
  const pauseButton = makeButton('暂停', '暂停朗读');
  const stopButton = makeButton('停止', '停止朗读');
  const closeButton = makeButton('关闭', '关闭朗读器');
  player.append(identity, speedLabel, pauseButton, stopButton, closeButton);
  shadow.append(style, fallbackLayer, selectionBar, player);
  document.documentElement.append(host);

  let selectedDetails = null;
  let session = null;
  let currentRange = null;

  function makeButton(text, label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = text;
    button.setAttribute('aria-label', label);
    return button;
  }

  function newSessionId() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  }

  function positionSelectionBar(details) {
    const width = 330;
    selectionBar.style.left = `${Math.max(
      12,
      Math.min(innerWidth - width - 12, details.rect.left + details.rect.width / 2 - width / 2),
    )}px`;
    selectionBar.style.top = `${Math.max(12, details.rect.top - 48)}px`;
    selectionBar.classList.add('visible');
  }

  function hideSelectionBar() {
    selectedDetails = null;
    selectionBar.classList.remove('visible');
  }

  function showPlayer(state, message) {
    player.classList.add('visible');
    status.textContent = message;
    pauseButton.hidden = !ACTIVE_STATES.has(state);
    stopButton.hidden = !ACTIVE_STATES.has(state);
    closeButton.hidden = ACTIVE_STATES.has(state);
    pauseButton.textContent = state === 'paused' ? '继续' : '暂停';
    pauseButton.setAttribute('aria-label', state === 'paused' ? '继续朗读' : '暂停朗读');
  }

  async function sendControl(type, details = {}) {
    if (!session) return {ok: false};
    return chrome.runtime.sendMessage({
      target: 'background',
      type,
      sessionId: session.id,
      ...details,
    });
  }

  async function startReading(queue, continuous) {
    if (!queue.length) {
      hideSelectionBar();
      showPlayer('error', '无法从此处识别可朗读的文字。');
      return;
    }
    if (session) await sendControl('STOP_READING').catch(() => {});
    QwenPageReader.clearHighlight(fallbackLayer);
    currentRange = null;
    session = {
      id: newSessionId(),
      queue,
      continuous,
      state: 'loading',
    };
    hideSelectionBar();
    window.getSelection()?.removeAllRanges();
    showPlayer('loading', '正在连接本地语音服务…');
    try {
      const response = await chrome.runtime.sendMessage({
        target: 'background',
        type: 'START_READING',
        sessionId: session.id,
        items: queue.map(({text}) => ({text})),
        speed: Number(speedSelect.value),
        continuous,
      });
      if (!response?.ok) throw new Error(response?.error || '无法连接扩展后台。');
    } catch (error) {
      session.state = 'error';
      showPlayer('error', error?.message || '无法连接扩展后台。');
    }
  }

  function stopReading() {
    if (session && ACTIVE_STATES.has(session.state)) void sendControl('STOP_READING');
    if (session) session.state = 'stopped';
    currentRange = null;
    QwenPageReader.clearHighlight(fallbackLayer);
    showPlayer('stopped', '已停止');
  }

  function updateSelection() {
    if (session && ACTIVE_STATES.has(session.state)) {
      hideSelectionBar();
      return;
    }
    requestAnimationFrame(() => {
      const details = QwenPageReader.selectionDetails();
      if (!details) {
        hideSelectionBar();
        return;
      }
      selectedDetails = details;
      positionSelectionBar(details);
    });
  }

  readSelectedButton.addEventListener('click', () => {
    if (selectedDetails) {
      void startReading([{
        text: selectedDetails.text,
        range: selectedDetails.range,
      }], false);
    }
  });
  readContinuousButton.addEventListener('click', () => {
    if (selectedDetails) {
      void startReading(
        QwenPageReader.readingQueueFromSelection(selectedDetails.range),
        true,
      );
    }
  });
  selectionBar.addEventListener('mousedown', (event) => event.preventDefault());
  pauseButton.addEventListener('click', () => {
    if (!session) return;
    const nextType = session.state === 'paused' ? 'RESUME_READING' : 'PAUSE_READING';
    void sendControl(nextType);
  });
  stopButton.addEventListener('click', stopReading);
  closeButton.addEventListener('click', () => {
    player.classList.remove('visible');
    session = null;
  });
  speedSelect.addEventListener('change', () => {
    const speed = Number(speedSelect.value);
    if (session && ALLOWED_SPEEDS.has(speed)) void sendControl('SET_SPEED', {speed});
  });

  document.addEventListener('mouseup', updateSelection);
  document.addEventListener('keyup', updateSelection);
  document.addEventListener('keydown', (event) => {
    const hasInteractiveTarget = event.composedPath().some(
      (target) => QwenPageReader.isEditableTarget(target),
    );
    if (
      event.code === 'Space'
      && !event.repeat
      && session?.continuous
      && ACTIVE_STATES.has(session.state)
      && !hasInteractiveTarget
    ) {
      event.preventDefault();
      const nextType = session.state === 'paused' ? 'RESUME_READING' : 'PAUSE_READING';
      void sendControl(nextType);
    }
    if (event.key === 'Escape' && session && ACTIVE_STATES.has(session.state)) {
      stopReading();
    }
  });
  window.addEventListener('scroll', () => {
    hideSelectionBar();
    if (currentRange) QwenPageReader.renderHighlight(currentRange, fallbackLayer);
  }, true);
  window.addEventListener('resize', () => {
    hideSelectionBar();
    if (currentRange) QwenPageReader.renderHighlight(currentRange, fallbackLayer);
  });
  window.addEventListener('pagehide', () => {
    if (session && ACTIVE_STATES.has(session.state)) void sendControl('STOP_READING');
  });

  chrome.runtime.onMessage.addListener((message) => {
    if (
      message?.target !== 'content'
      || !session
      || message.sessionId !== session.id
      || message.type !== 'READING_EVENT'
    ) {
      return;
    }
    if (
      message.event === 'SENTENCE_STARTED'
      && Number.isInteger(message.index)
      && message.index >= 0
      && message.index < session.queue.length
    ) {
      currentRange = session.queue[message.index].range;
      QwenPageReader.highlightAndCenter(currentRange, fallbackLayer);
    } else if (message.event === 'STATE_CHANGED') {
      const validStates = new Set(['loading', 'paused', 'playing', 'stopped']);
      if (!validStates.has(message.state) || typeof message.message !== 'string') return;
      session.state = message.state;
      showPlayer(message.state, message.message.slice(0, 240));
      if (message.state === 'stopped') {
        currentRange = null;
        QwenPageReader.clearHighlight(fallbackLayer);
      }
    } else if (message.event === 'READING_FINISHED') {
      session.state = 'stopped';
      currentRange = null;
      QwenPageReader.clearHighlight(fallbackLayer);
      showPlayer('stopped', session.continuous ? '连续朗读完成' : '朗读完成');
    } else if (
      message.event === 'READING_ERROR'
      && typeof message.message === 'string'
    ) {
      session.state = 'error';
      currentRange = null;
      QwenPageReader.clearHighlight(fallbackLayer);
      showPlayer('error', message.message.slice(0, 240));
    }
  });
})();
