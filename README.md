# PDF Book Site

把带文本层的 PDF 书籍在本机转换成可阅读、可搜索、可生产构建的
Docusaurus 文档站。转换过程不会上传 PDF；默认先使用 PyMuPDF 做审计和
确定性解析，可选安装 Docling 生成表格、公式、代码和图片结构的对照产物。

本项目已用 `Generative_AI_with_LangChain_2e_-_Leonid_Kuligin.pdf`
前 100 页完成端到端验收：生成 9 个章节文档、15 个图片引用（14 个去重文件）
和 100 条页面
质量记录，Docusaurus 生产构建及桌面/移动端浏览器检查均通过。

## 环境要求

- macOS 或 Linux
- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- [pnpm](https://pnpm.io/installation)

```bash
cd /Users/conermoltbot/Documents/pdf-book-site
uv sync --extra dev
uv run booksite doctor
```

`pipeline.yaml` 是可立即运行的轻量配置，不要求下载模型。需要更高保真解析时：

```bash
uv sync --extra dev --extra docling
cp pipeline.example.yaml pipeline.yaml
```

Docling 仍在本机执行，示例配置关闭 OCR，避免对整本书做无必要的识别。

## 转换任意 PDF

一次完成审计、解析、站点生成、质量报告和生产构建：

```bash
uv run booksite all /绝对路径/你的书.pdf \
  --config pipeline.yaml \
  --output site
```

`--output site` 表示书籍集合根目录。每本 PDF 会自动写入独立的
`site/<规范化PDF名称>-<内容哈希前8位>/`，例如：

```text
site/
├── generative-ai-with-langchain-2e-leonid-kuligin-0f79b523/
└── another-book-a1b2c3d4/
```

转换另一份 PDF 不会覆盖、清理或混入已有书籍；每个目录还保存完整 SHA-256
所有权清单以防短哈希碰撞。重复转换会先在临时目录完成生成、校验和构建，成功
后才替换同一本书的旧站点，因此中途失败仍保留上一次可用版本。命令结束时输出
的 `Site:` 路径就是该书的实际目录。

旧版本若曾直接生成 `site/docs`、`site/build` 或 `site/package.json`，新版会
拒绝在混合目录继续写入，并给出迁移提示。先把旧站整体移到备份目录，再重新
运行转换即可。

只转换前 100 页：

```bash
uv run booksite all /绝对路径/你的书.pdf \
  --config pipeline.yaml \
  --output site \
  --max-pages 100
```

构建完成后，macOS 可双击该书目录中的启动器：

```bash
open site/<book-id>/打开网站.command
```

它会启动仅监听本机的 HTTP 服务并自动打开浏览器。阅读期间保持终端窗口开启，
按 `Control-C` 停止。请勿直接双击该书的 `build/index.html`：Docusaurus 的
静态资源和页面路由需要通过 HTTP 访问，`file://` 会导致页面加载失败，把
`baseUrl` 改成本机文件路径也无法正确部署。

也可以使用命令行预览：

```bash
uv run --no-project --python 3.12 --with 'mlx-audio==0.4.5' \
  python site/<book-id>/serve-local.py
# 或使用 Docusaurus 自带的预览服务
pnpm --dir site/<book-id> serve
```

浏览器访问命令输出的本地地址。生成站点包括：

- 左侧全书目录、正文阅读区、右侧页内目录
- KaTeX 数学公式和带复制按钮的代码块
- 保留代码缩进、代码空行、嵌套列表层级及标题所在的正文顺序
- 完全离线的章节级全文搜索
- 图片抽取和无文本页面的渲染回退
- PDF 原始页码溯源
- `/quality-report` 页面及 JSON、CSV、HTML 报告
- 选中文字后的本地 Qwen3-TTS 朗读、暂停/继续/停止和 0.75–1.5× 调速
- 深色模式和移动端侧栏

朗读功能会自动发现并复用 PDFgear 已下载的
`mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit`，不会复制或再次下载约
1.9 GB 的模型。首次使用可能由 `uv` 安装约 100 MB 的 MLX 运行库。选中文字、
参考音色和生成音频都只在本机处理；服务仅允许绑定和访问回环地址。没有模型、
MLX 运行库或 `uv` 时，网站仍可正常阅读，并会显示可操作的朗读错误提示。启动
脚本会先预热模型；朗读时通过 Web Audio 播放正在生成的音频块，不必等待整段
语音生成完成。

## 分阶段运行

```bash
uv run booksite audit book.pdf --max-pages 100
uv run booksite parse book.pdf --max-pages 100
uv run booksite assemble book.pdf --max-pages 100
uv run booksite generate-site book.pdf --output site --max-pages 100
uv run booksite validate book.pdf --output site --max-pages 100
```

缓存位于 `workspace/cache/`。相同 PDF、页数范围和配置会复用审计与 BookIR。
`--force-page 32` 可使当前书籍缓存失效并重新处理，同时校验目标页码有效性。
当前 MVP 会重新装配该书的章节，而不是仅写入单页；真正的单页增量装配列在后续
改进项中。

## 输出目录

```text
site/                       全部已生成书籍的集合根目录
site/<book-id>/             一份 PDF 的独立 Docusaurus 站点
site/<book-id>/build/       该书可部署的静态文件（本地需通过 HTTP 打开）
site/<book-id>/打开网站.command
                            该书的 macOS 双击预览入口
site/<book-id>/serve-local.py
                            该书无第三方依赖的本地预览服务器
workspace/cache/            可恢复的阶段缓存
workspace/intermediate/     audit.json、BookIR、可选 Docling 产物
workspace/reports/          summary.json、HTML、CSV、warnings、构建日志
design/                     已接受的阅读器视觉概念稿
docs/                       规格与设计系统
src/booksite/               转换器和 CLI
tests/                      单元与集成测试
```

PDF、生成的书籍内容、缓存、模型和 `site/` 均不进入 Git。请只发布你拥有相应
版权或授权的内容。

## 解析策略

1. PyMuPDF 读取元数据、书签、文本块、字体、链接和图片，并给每页分类。
2. 原生文本解析器执行 Unicode NFC、保守断词合并、重复页眉页脚移除和章节装配。
3. 安装并启用 Docling 时，额外生成高保真 JSON、Markdown 和 HTML 中间产物；
   当前版本不会自动用它覆盖原生章节。
4. MinerU 与 OvisOCR2 通过隔离子进程协议预留，不会自动下载模型或整书 OCR。
5. BookIR 经 Pydantic 校验后生成 Docusaurus、离线搜索索引和质量报告。
6. `pnpm build` 是硬性验收门；断链、缺图或 MDX 错误会导致命令失败。

核心接口和取舍见 [规格](docs/spec.md)，视觉约束见
[设计系统](docs/design-system.md)。实现依据包括
[Docusaurus 文档](https://docusaurus.io/docs/docs-introduction/)、
[Docling 转换器](https://docling-project.github.io/docling/reference/document_converter/)、
[PyMuPDF 文档](https://pymupdf.readthedocs.io/) 和
[Typer 文档](https://typer.tiangolo.com/)。

## 测试与质量门

```bash
uv run pytest
uv run ruff check .
BOOKSITE_PNPM="$(command -v pnpm)" \
  uv run booksite all /path/to/book.pdf --config pipeline.yaml --output site --max-pages 100
```

样例验收结果：

| 指标 | 结果 |
|---|---:|
| 处理页数 | 100 |
| 章节 | 9 |
| 图片引用 / 去重文件 | 15 / 14 |
| 平均质量分 | 0.952 |
| 建议人工复核页 | 12 |
| Python 测试 | 全部通过 |
| Docusaurus build | 通过 |
| 浏览器控制台错误 | 0 |

## 当前边界

- 轻量模式优先服务有可用文本层的 PDF；扫描书应配置独立 OCR 引擎。
- 原生解析对复杂跨页表格和公式只做保守处理；高保真需求请启用 Docling。
- Docling 产物目前用于对照和后续回填，自动合并到 BookIR 仍是后续工作。
- MinerU/OvisOCR2 适配器已具备超时、JSON 协议和隔离边界，但模型安装与
  块级回填仍是后续工作。
- 当前可调整且实际生效的配置仅为 `pdf.fallback_render_dpi` 与 `docling.*`；
  其他预留字段若改成非默认值会明确报错，不会静默忽略。
- 解析忠实保留原文，不做翻译、改写或事实纠正。
