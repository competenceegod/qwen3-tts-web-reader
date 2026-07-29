# Spec: PDF Book to Docusaurus

## Objective

Build a local-first CLI that converts text-layer PDF books into a readable,
searchable, static Docusaurus documentation site. The first release prioritizes
semantic reading quality over pixel-perfect PDF reproduction.

Primary user story:

> As a developer with a PDF book, I can run one command and receive a
> production-buildable website with a full-book sidebar, readable chapter
> pages, an on-page table of contents, source-page traceability, and a quality
> report.

## Scope and assumptions

- The MVP supports PDFs with a usable native text layer.
- PyMuPDF is always available in the core environment and performs audit,
  native-text extraction, bookmarks, block geometry, image extraction, and
  page rendering.
- Docling produces high-fidelity comparison artifacts when the optional
  `docling` dependency is installed. The MVP keeps the core native-text parser
  as the deterministic BookIR source; automatic Docling block replacement is
  deferred.
- MinerU and OvisOCR2 are optional, isolated subprocess adapters. The MVP
  validates their protocol and routing but does not download their model
  weights automatically.
- The sample validation run processes PDF pages 1-100 inclusive from
  `Generative_AI_with_LangChain_2e_-_Leonid_Kuligin.pdf`.
- All parsing is local. The tool never uploads PDF bytes or rendered pages.
- The generated book content remains the user's responsibility with respect to
  copyright and publication rights.

## Tech stack

- Python 3.11+
- PyMuPDF 1.28.0
- Pydantic 2
- Typer
- PyYAML
- Optional Docling 2.116.0
- pytest and Ruff
- Node.js 20+
- Docusaurus 3.10.2
- remark-math 6, rehype-katex 7, KaTeX

## Commands

```bash
# Python environment
python3 -m venv .venv-core
.venv-core/bin/pip install -e '.[dev]'

# Diagnostics and individual pipeline phases
.venv-core/bin/booksite doctor
.venv-core/bin/booksite audit input.pdf --max-pages 100
.venv-core/bin/booksite parse input.pdf --max-pages 100
.venv-core/bin/booksite assemble input.pdf --max-pages 100
.venv-core/bin/booksite generate-site input.pdf --max-pages 100
.venv-core/bin/booksite validate input.pdf --max-pages 100

# End-to-end conversion
.venv-core/bin/booksite all input.pdf \
  --config pipeline.yaml \
  --output workspace/output/book \
  --max-pages 100

# Targeted reprocessing
.venv-core/bin/booksite all input.pdf \
  --config pipeline.yaml \
  --output workspace/output/book \
  --force-page 32

# Quality gates
.venv-core/bin/pytest
.venv-core/bin/ruff check .
pnpm --dir site build
pnpm --dir site serve
```

## Project structure

```text
src/booksite/       Python CLI and conversion pipeline
tests/              Unit and integration tests
templates/          Generated-site templates and static resources
site/               Docusaurus application populated by the last run
workspace/          Ignored inputs, cache, intermediates, reports, outputs
docs/               Specification and design decisions
design/             Accepted UI concept
```

## Code style

Use small typed functions, Pydantic models at data boundaries, `pathlib.Path`
for paths, and explicit dependency injection for subprocess runners.

```python
def stable_slug(title: str, source_page: int) -> str:
    normalized = normalize_title(title)
    suffix = short_hash(f"{source_page}:{title}")
    return f"{normalized}-{suffix}"
```

## Testing strategy

- Unit tests cover stable slugs, Unicode NFC cleanup, conservative
  dehyphenation, repeated header/footer detection, quality classification,
  subprocess adapter validation, cache keys, and MDX escaping.
- Integration tests build a small synthetic PDF, run the native pipeline, and
  assert BookIR, Markdown, report, and Docusaurus outputs.
- The real sample PDF is an explicit end-to-end acceptance run limited to the
  first 100 pages.
- Docusaurus production build is a hard gate.
- Browser verification checks the home document, left sidebar, right TOC,
  multiple generated pages, source-page labels, desktop layout, and mobile
  overflow.

## Boundaries

### Always

- Validate configuration and intermediate artifacts with Pydantic.
- Use atomic writes for cache and generated JSON.
- Preserve original wording and language.
- Record page provenance and automatic transformations.
- Reuse cached stages unless invalidated.
- Keep external engines behind a common adapter protocol and timeout.

### Ask first

- Uploading any source material to a remote service.
- Installing or downloading multi-gigabyte OCR/model weights.
- Replacing the sample book's text with rewritten or translated content.

### Never

- Hard-code a user home directory, model directory, or model ID.
- Run whole-book OCR by default.
- Allow one failed page to delete previously completed work.
- Commit PDFs, generated book content, caches, model files, or secrets.

## Success criteria

- One command converts a text-layer PDF into a generated Docusaurus site.
- The production Docusaurus build succeeds.
- Every processed PDF page has a PageIR record, including empty-text pages.
- All in-range PDF bookmarks appear in the resolved table of contents.
- Stable slugs do not change across identical runs.
- Every emitted image reference resolves to a file.
- Repeated headers, footers, and page numbers are excluded from body Markdown
  and listed in a removal report.
- The pipeline resumes from cache and accepts `--force-page`.
- A JSON and HTML quality report is generated locally.
- The sample book's first 100 pages pass Python tests, content validation,
  Docusaurus build, and browser smoke checks.

## Deferred after MVP

- Full MinerU block-level replacement.
- Automatic Docling block selection and BookIR replacement.
- OvisOCR2 model installation and Apple Silicon weight management.
- Advanced cross-page table reconstruction.
- Formula-image fallback derived from model-detected formula boxes.
- Pixel-diff visual regression baselines for arbitrary generated books.

## Open questions

None blocking. Optional OCR engines require user-supplied executables and model
configuration when enabled.
