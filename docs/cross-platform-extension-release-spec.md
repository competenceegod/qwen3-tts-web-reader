# Spec: Qwen3-TTS 网页朗读扩展跨平台发布

## Objective

把现有 Chrome/Chromium Manifest V3 扩展发布为可重复构建的 macOS、Windows
和 Linux 三个平台包。扩展代码保持一致；平台包只在本地语音运行时、启动器和说明上
存在差异。发布前必须经过自动化测试、真实 Chrome 验收、安全检查和产物审计。

## Scope

- 版本提升到 `0.2.0`。
- 生成 `qwen3-tts-web-reader-0.2.0-{macos,windows,linux}.zip`。
- 每个压缩包都包含可直接“加载已解压”的 `extension/`、本地服务源码、平台启动器、
  中文安装说明和许可证。
- macOS 使用 MLX Audio 的低延迟路径，并由本项目独立下载
  `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-bf16`；不要求安装 PDFgear，
  也不读取 PDFgear 的应用容器、模型或参考音频。
- Windows/Linux 默认使用 Qwen 官方 `qwen-tts` 包和
  `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` 模型；首次启动按官方机制下载模型。
- Windows/Linux 优先使用 NVIDIA CUDA，无法使用 CUDA 时允许 CPU 回退，但明确提示
  CPU 首次生成和逐句生成会明显更慢。
- 不内置模型、PDFgear 资源、用户文字、生成音频、密钥或机器路径。

## Runtime contract

本地服务继续只绑定 `127.0.0.1:8765`，并保持已有 HTTP API：

- `GET /api/tts/status`
- `POST /api/tts` with `{ "text": "..." }`
- `GET /api/tts/stream/{one-time-token}`

后端由 `--tts-backend auto|mlx|torch` 选择：

- `auto`：macOS 使用独立的 MLX/Qwen 模型；Windows/Linux 使用官方 PyTorch/Qwen 后端。
- `mlx`：要求本机存在 `mlx-audio` 和完整 MLX 模型。
- `torch`：要求本机存在 `qwen-tts`；模型、speaker 和 device 可由环境变量覆盖。

所有后端都必须实现相同的 `status`、`require_available`、`stream_pcm`、`sample_rate`
和 `warm_up` 接口。官方 PyTorch API当前返回整句音频而非真正的增量音频，因此该后端
会在整句生成后返回一个 PCM 块；扩展层的队列、暂停恢复、高亮和自动滚动行为不变。

## Packaging contract

每个平台包的顶层目录名固定，并包含：

```text
qwen3-tts-web-reader-0.2.0-<platform>/
  extension/
  service/local_server.py
  README.md
  LICENSE
  start-qwen-reader.command   # macOS only
  start-qwen-reader.ps1      # Windows only
  start-qwen-reader.cmd      # Windows convenience wrapper
  start-qwen-reader.sh       # Linux only
```

打包器必须使用标准库、固定文件清单、规范化 ZIP 路径和固定时间戳，使相同提交生成的
产物字节可重复。脚本必须拒绝符号链接、路径逃逸和缺失文件。

## CI and release

- GitHub Actions 在 `ubuntu-latest`、`macos-latest`、`windows-latest` 上运行测试。
- 三个平台都验证 Python 测试、JavaScript 语法和打包内容；Linux 额外运行 Ruff。
- CI 不下载数 GB 模型，也不声称执行了 Windows/Linux 的真实模型推理。
- tag `v0.2.0` 触发发布工作流，重新执行质量门禁、构建三份确定性 ZIP、生成 SHA-256
  校验文件，并通过 GitHub CLI 上传 Release。
- 本机 macOS 在发布前执行真实 Qwen 服务状态检查与独立 Chrome 扩展验收。

## Security boundaries

- 扩展仅拥有回环地址的 host permissions；不增加 tabs、history、cookies、clipboard。
- 服务拒绝非回环客户端、非 JSON、超长文本和过期/复用 token。
- 启动器不接受网页传入的 shell 参数，不使用 `eval`，不以管理员/root 身份运行。
- 发布包中禁止 `.env`、缓存、模型、音频、PDF、构建站点和绝对用户路径。
- GitHub 工作流只使用仓库自带 `GITHUB_TOKEN`；不提交或输出额外凭据。

## Acceptance criteria

1. 三个平台包都能构建两次并得到相同 SHA-256。
2. 所有包都包含同一版本的 MV3 扩展和正确的平台启动器；行尾与可执行位符合平台。
3. 后端自动选择、缺失依赖提示、CUDA/CPU 设备选择和 PyTorch 音频转换都有单元测试。
4. 原有连续朗读、长暂停恢复、回压、低能量杂音过滤和本地 API 测试无回归。
5. `pytest`、Ruff、所有 JavaScript `node --check`、工作流/manifest JSON 检查通过。
6. 真实 Chrome 中能在普通网页选择文字、显示朗读控制、与本地服务连接且无控制台错误。
7. 发布包经过路径、秘密、绝对路径、远程代码和 SHA-256 审计。
8. GitHub Release 包含三份 ZIP、校验文件、平台要求和已知性能差异。

## Out of scope

- Chrome Web Store、Edge Add-ons、Firefox AMO 和 Safari App Store 发布。
- 在 CI 中下载模型或租用三种系统的 GPU 做生成质量基准。
- 保证 CPU 推理达到 PDFgear/Apple Silicon MLX 的首句延迟。
- 自动安装显卡驱动、CUDA Toolkit、Chrome 或系统级 `uv`。
