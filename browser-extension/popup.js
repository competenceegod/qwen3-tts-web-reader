(() => {
  'use strict';

  const STATUS_URL = 'http://127.0.0.1:8765/api/tts/status';
  const status = document.getElementById('status');
  const retry = document.getElementById('retry');

  async function checkService() {
    status.classList.remove('ready');
    status.textContent = '正在检查本地服务…';
    try {
      const response = await fetch(STATUS_URL, {cache: 'no-store'});
      const payload = await response.json();
      if (!response.ok || payload.available !== true) {
        throw new Error('模型或运行库不可用');
      }
      status.classList.add('ready');
      status.textContent = '本地 Qwen3-TTS 服务已就绪';
    } catch {
      status.textContent = '服务未启动，请运行当前系统的 Qwen 启动器';
    }
  }

  retry.addEventListener('click', () => void checkService());
  void checkService();
})();
