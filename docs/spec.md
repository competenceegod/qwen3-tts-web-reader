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

Additional output and fidelity requirements:

- `--output` identifies a collection root. Each PDF is generated into
  `<output>/<normalized-pdf-name>-<source-hash>/` so converting another PDF
  cannot overwrite or mix with an existing book.
- A full-hash manifest verifies directory ownership; path traversal, symbolic
  link targets, short-hash collisions, and legacy flat roots are rejected.
- Reprocessing the same PDF updates only its stable book directory, using
  staging and promotion so a failed rerun preserves the previous site.
- Monospace code keeps PDF-leading indentation, including short delimiter
  lines and intentional blank lines. Bullet glyphs are emitted as semantic
  Markdown lists, adjacent list blocks remain one list, and PDF x coordinates
  restore nested list levels.
- Bookmark headings are emitted at their matching PDF block position, not
  unconditionally at the beginning of the source page.
- Code blocks preserve the PDF's span-level foreground colors, italic/bold
  emphasis, declared monospace family, point-size ratio, background fill,
  accent rule, line indentation, and intentional blank lines. The generated
  reader must not recolor these blocks through the active Prism theme.
- PDF-styled code remains usable on the web: it supports copy-to-clipboard,
  horizontal scrolling without page overflow, and an accessible text
  representation. If the declared PDF font is unavailable, the reader falls
  back to a local system monospace font without fetching remote assets.

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
  --output site \
  --max-pages 100

# Targeted reprocessing
.venv-core/bin/booksite all input.pdf \
  --config pipeline.yaml \
  --output site \
  --force-page 32

# Quality gates
.venv-core/bin/pytest
.venv-core/bin/ruff check .
pnpm --dir site/<book-id> build
pnpm --dir site/<book-id> serve

# Open the production build locally on macOS
open site/<book-id>/打开网站.command
```

## Project structure

```text
src/booksite/       Python CLI and conversion pipeline
tests/              Unit and integration tests
templates/          Generated-site templates and static resources
site/               Collection root containing one isolated directory per PDF
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
- Output-isolation tests convert two PDFs into one collection root and assert
  both independently generated sites remain intact.
- The real sample PDF is an explicit end-to-end acceptance run limited to the
  first 100 pages.
- Docusaurus production build is a hard gate.
- Generated sites include a dependency-free local HTTP preview server and a
  macOS double-click launcher. Direct `file://` access to `build/index.html` is
  unsupported because Docusaurus emits site-root asset and route URLs.
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
- Different PDFs written to the same output root produce different stable
  book directories and never delete or reuse each other's content; full source
  hashes remain authoritative if readable IDs collide.
- Code indentation and semantic list structure are preserved in generated
  Markdown and rendered HTML.
- Same-level PDF list items keep the same nesting and marker style when rich
  blocks such as styled code appear between them; those rich blocks remain
  children of the preceding list item.
- Layout-only hyphenation is removed from list continuations and recognized
  multi-block callouts.
- At least one light and one dark code surface from the sample PDF render with
  foreground/background colors matching their PDF drawing and text-span data.
- Mixed prose-and-URL callouts are emitted as one shaded callout with a complete
  clickable URL, without misclassifying the prose or URL continuation as
  separate copyable code blocks.
- The production Docusaurus build succeeds.
- A generated production build can be opened through the bundled local preview
  launcher without changing `baseUrl` to a machine-specific file path.
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
