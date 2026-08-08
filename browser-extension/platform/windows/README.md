# Windows 安装说明

适用于 Windows 10/11 和 Chrome、Edge 等 Chromium 浏览器。

1. 安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)。
2. 双击 `start-qwen-reader.cmd`。
3. 首次运行会安装 Qwen 官方 `qwen-tts` Python 包并下载约 1–3 GB 模型。
4. 看到 `本地语音服务：http://127.0.0.1:8765/` 后保持窗口开启。
5. 打开 `chrome://extensions`，启用开发者模式，点击“加载已解压的扩展程序”，
   选择本包的 `extension` 目录。

启动器会优先使用 PyTorch 可识别的 NVIDIA CUDA 显卡。没有 CUDA 时自动使用 CPU；
CPU 可以运行，但首句和逐句生成可能很慢。若要使用 NVIDIA GPU，请先按 PyTorch
官方说明安装与你的驱动匹配的 CUDA 版 PyTorch，再启动本服务。

快捷键：Space 暂停/继续，Esc 停止。

可选配置：`BOOKSITE_TTS_DEVICE=cpu|cuda|cuda:0`、
`BOOKSITE_TTS_SPEAKER=Ryan`、`BOOKSITE_TTS_TORCH_MODEL=<本地路径或模型ID>`。
