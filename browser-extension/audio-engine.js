const SERVICE_ORIGIN = 'http://127.0.0.1:8765';
const SAMPLE_RATE = 24000;
const INITIAL_BUFFER_SECONDS = 0.35;
const MAX_BUFFER_AHEAD_SECONDS = 10;
const BUFFER_CAPACITY_RESERVE_SECONDS = 1;
const REBUFFER_SECONDS = 0.12;
const SENTENCE_CROSSFADE_SECONDS = 0.008;
const START_FADE_SECONDS = 0.006;
const BUSY_RETRY_DELAYS_MS = Object.freeze([150, 300, 600, 1000, 1500, 2000]);
const ALLOWED_SPEEDS = new Set([0.75, 1, 1.25, 1.5]);

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
      clearTimeout(timer);
      reject(abortError());
    }
    const timer = setTimeout(() => {
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

async function requestStreamUrl(
  text,
  {
    request = fetch,
    signal,
  } = {},
) {
  const response = await request(`${SERVICE_ORIGIN}/api/tts`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text}),
    signal,
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
  return payload.streamUrl;
}

export async function requestAudioStream(
  text,
  {
    request = fetch,
    retryDelays = BUSY_RETRY_DELAYS_MS,
    signal,
  } = {},
) {
  const requestSignal = signal ?? new AbortController().signal;
  let attempt = 0;
  while (true) {
    const streamUrl = await requestStreamUrl(
      text,
      {request, signal: requestSignal},
    );
    const response = await request(
      `${SERVICE_ORIGIN}${streamUrl}`,
      {signal: requestSignal},
    );
    if (response.status === 409 && attempt < retryDelays.length) {
      await response.arrayBuffer().catch(() => {});
      await abortableDelay(retryDelays[attempt], requestSignal);
      attempt += 1;
      continue;
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `本地音频流返回 ${response.status}`);
    }
    if (!response.body) throw new Error('本地音频流没有返回内容。');
    return response;
  }
}

export class StreamingTtsPlayer {
  constructor() {
    this.audioContext = null;
    this.audioSources = new Set();
    this.pendingPlayback = new Set();
    this.controller = null;
    this.playbackId = 0;
    this.speed = 1;
  }

  async start(items, {speed, onSentenceStarted}) {
    this.stop();
    this.speed = ALLOWED_SPEEDS.has(speed) ? speed : 1;
    const controller = new AbortController();
    this.controller = controller;
    const playbackId = this.playbackId;
    const audioContext = new AudioContext();
    this.audioContext = audioContext;
    await audioContext.resume();
    const timeline = {hasAudio: false, nextStartTime: 0};
    const playbackPromises = [];

    try {
      for (let index = 0; index < items.length; index += 1) {
        if (controller.signal.aborted) throw abortError();
        await waitForBufferCapacity(audioContext, timeline, controller.signal);
        const {playbackComplete} = await this.enqueueStream({
          audioContext,
          controller,
          index,
          onSentenceStarted,
          playbackId,
          text: items[index].text,
          timeline,
        });
        playbackPromises.push(playbackComplete);
      }
      await Promise.all(playbackPromises);
      if (controller.signal.aborted || this.playbackId !== playbackId) throw abortError();
    } finally {
      if (this.controller === controller) this.controller = null;
    }
  }

  async enqueueStream({
    audioContext,
    controller,
    index: sentenceIndex,
    onSentenceStarted,
    playbackId,
    text,
    timeline,
  }) {
    const streamResponse = await requestAudioStream(
      text,
      {signal: controller.signal},
    );

    const localSources = new Set();
    let resolvePlayback;
    let playbackResolved = false;
    const playbackComplete = new Promise((resolve) => {
      resolvePlayback = resolve;
    });
    const resolvePlaybackOnce = () => {
      if (playbackResolved) return;
      playbackResolved = true;
      this.pendingPlayback.delete(resolvePlaybackOnce);
      resolvePlayback();
    };
    this.pendingPlayback.add(resolvePlaybackOnce);
    const reader = streamResponse.body.getReader();
    let headerBytesRemaining = 44;
    let leftover = new Uint8Array(0);
    let receivedAudio = false;
    let streamFinished = false;
    let lastSentenceGain = null;
    let lastSentenceEndTime = 0;

    const finishIfReady = () => {
      if (
        streamFinished
        && localSources.size === 0
        && this.playbackId === playbackId
      ) {
        resolvePlaybackOnce();
      }
    };

    const schedulePcm = (pcmBytes) => {
      const combined = new Uint8Array(leftover.length + pcmBytes.length);
      combined.set(leftover);
      combined.set(pcmBytes, leftover.length);
      const usableLength = combined.length - (combined.length % 2);
      leftover = combined.slice(usableLength);
      if (!usableLength) return;

      const samples = new Float32Array(usableLength / 2);
      const view = new DataView(combined.buffer, combined.byteOffset, usableLength);
      for (let sampleIndex = 0; sampleIndex < samples.length; sampleIndex += 1) {
        samples[sampleIndex] = view.getInt16(sampleIndex * 2, true) / 32768;
      }
      const buffer = audioContext.createBuffer(1, samples.length, SAMPLE_RATE);
      buffer.copyToChannel(samples, 0);
      const source = audioContext.createBufferSource();
      const gainNode = audioContext.createGain();
      const playbackRate = this.speed;
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
      this.audioSources.add(source);
      source.onended = () => {
        localSources.delete(source);
        this.audioSources.delete(source);
        source.disconnect();
        gainNode.disconnect();
        finishIfReady();
      };
      source.start(startAt);
      if (isFirstSentenceBlock) {
        receivedAudio = true;
        void waitUntilAudioTime(audioContext, startAt, controller.signal)
          .then(() => {
            if (this.playbackId === playbackId) onSentenceStarted(sentenceIndex);
          })
          .catch(() => {});
      }
    };

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
    if (controller.signal.aborted || this.playbackId !== playbackId) throw abortError();
    return {playbackComplete};
  }

  async pause() {
    if (this.audioContext?.state === 'running') await this.audioContext.suspend();
  }

  async resume() {
    const context = this.audioContext;
    if (!context || context.state === 'closed') return false;
    if (context.state !== 'running') await context.resume();
    return context.state === 'running';
  }

  setSpeed(speed) {
    if (ALLOWED_SPEEDS.has(speed)) this.speed = speed;
  }

  stop() {
    this.playbackId += 1;
    this.controller?.abort();
    this.controller = null;
    for (const resolve of this.pendingPlayback) resolve();
    this.pendingPlayback.clear();
    for (const source of this.audioSources) {
      source.onended = null;
      try {
        source.stop();
      } catch {
        // A source that already ended cannot be stopped again.
      }
    }
    this.audioSources.clear();
    const context = this.audioContext;
    this.audioContext = null;
    if (context && context.state !== 'closed') void context.close();
  }
}
