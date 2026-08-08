# macOS 安装说明

适用于 Apple Silicon（M1 或更新）和 Chrome、Edge 等 Chromium 浏览器。

1. 安装 [uv](https://docs.astral.sh/uv/)。
2. 双击 `start-qwen-reader.command`；macOS 若阻止首次运行，请右键选择“打开”。
3. 首次运行会独立下载 MLX Audio 和约 1–3 GB 的 Qwen3-TTS 模型，请保持联网。
4. 看到 `本地语音服务：http://127.0.0.1:8765/` 后保持终端窗口开启。
5. 打开 `chrome://extensions`，启用开发者模式，点击“加载已解压的扩展程序”，
   选择本包的 `extension` 目录。

本版本不要求安装 PDFgear，也不会读取 PDFgear 的模型、容器或参考音频。模型由
MLX Audio 从 Hugging Face 下载到当前用户的标准缓存，之后可以离线使用。

快捷键：选择文字后可单次朗读或从选择处连续朗读；Space 暂停/继续，Esc 停止。

可选配置：启动前设置 `BOOKSITE_TTS_SPEAKER`（默认 `Ryan`）或
`BOOKSITE_TTS_MLX_MODEL` 可更换 MLX Qwen 模型。
