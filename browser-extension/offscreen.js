import {StreamingTtsPlayer} from './audio-engine.js';

const player = new StreamingTtsPlayer();
let active = null;

function emit(tabId, sessionId, event, details = {}) {
  void chrome.runtime.sendMessage({
    target: 'background',
    type: 'READING_EVENT',
    tabId,
    sessionId,
    event,
    ...details,
  });
}

function stopActive({notify = false} = {}) {
  if (!active) return;
  const previous = active;
  active = null;
  player.stop();
  if (notify) emit(previous.tabId, previous.sessionId, 'STATE_CHANGED', {
    state: 'stopped',
    message: '已停止',
  });
}

async function startReading(message) {
  stopActive();
  const session = {
    continuous: message.continuous,
    sessionId: message.sessionId,
    tabId: message.tabId,
    itemCount: message.items.length,
  };
  active = session;
  emit(session.tabId, session.sessionId, 'STATE_CHANGED', {
    state: 'loading',
    message: '正在生成首段语音…',
  });
  try {
    await player.start(message.items, {
      speed: message.speed,
      onSentenceStarted(index) {
        if (active !== session) return;
        emit(session.tabId, session.sessionId, 'SENTENCE_STARTED', {index});
        emit(session.tabId, session.sessionId, 'STATE_CHANGED', {
          state: 'playing',
          message: session.continuous
            ? `正在连续朗读 · 第 ${index + 1}/${session.itemCount} 句`
            : '正在朗读',
        });
      },
    });
    if (active !== session) return;
    active = null;
    player.stop();
    emit(session.tabId, session.sessionId, 'READING_FINISHED');
  } catch (error) {
    if (error?.name === 'AbortError' || active !== session) return;
    active = null;
    player.stop();
    emit(session.tabId, session.sessionId, 'READING_ERROR', {
      message: String(error?.message || '本地语音生成失败。').slice(0, 240),
    });
  }
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.target !== 'offscreen') return;
  if (message.type === 'START_READING') {
    void startReading(message);
    return;
  }
  if (!active || message.sessionId !== active.sessionId) return;
  if (message.type === 'STOP_READING') {
    stopActive({notify: true});
  } else if (message.type === 'PAUSE_READING') {
    void player.pause().then(() => {
      if (active) emit(active.tabId, active.sessionId, 'STATE_CHANGED', {
        state: 'paused',
        message: '已暂停 · 空格键继续',
      });
    });
  } else if (message.type === 'RESUME_READING') {
    void player.resume().then(() => {
      if (active) emit(active.tabId, active.sessionId, 'STATE_CHANGED', {
        state: 'playing',
        message: '正在连续朗读',
      });
    });
  } else if (message.type === 'SET_SPEED') {
    player.setSpeed(message.speed);
  }
});
