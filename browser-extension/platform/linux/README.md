# Linux 安装说明

适用于主流 x86_64 Linux 发行版和 Chrome、Chromium、Edge。

1. 安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)。
2. 在终端运行 `./start-qwen-reader.sh`。
3. 首次运行会安装 Qwen 官方 `qwen-tts` Python 包并下载约 1–3 GB 模型。
4. 看到 `本地语音服务：http://127.0.0.1:8765/` 后保持终端开启。
5. 打开 `chrome://extensions`，启用开发者模式，点击“加载已解压的扩展程序”，
   选择本包的 `extension` 目录。

启动器会优先使用 PyTorch 可识别的 NVIDIA CUDA 显卡。没有 CUDA 时自动使用 CPU；
CPU 可以运行，但首句和逐句生成可能很慢。发行版若缺少 SoX，请通过系统包管理器
安装 `sox` 后重试。

快捷键：Space 暂停/继续，Esc 停止。

可选配置：`BOOKSITE_TTS_DEVICE=cpu|cuda|cuda:0`、
`BOOKSITE_TTS_SPEAKER=Ryan`、`BOOKSITE_TTS_TORCH_MODEL=<本地路径或模型ID>`。
