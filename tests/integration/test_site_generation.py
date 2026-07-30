import json
import stat
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

from booksite.models.book_ir import BookIR, SectionIR
from booksite.site.docusaurus import generate_docusaurus_site


def test_generate_docusaurus_site_writes_docs_navigation_and_report_link(tmp_path: Path) -> None:
    book = BookIR(
        book_id="sample-12345678",
        source_pdf="sample.pdf",
        source_sha256="1" * 64,
        title="Sample 'Book'\nLine",
        page_count=2,
        pages=[],
        sections=[
            SectionIR(
                section_id="chapter-1-aaaaaaaa",
                title="Chapter 1",
                level=1,
                slug="chapter-1-aaaaaaaa",
                order=1,
                source_pages=[1, 2],
                markdown="# Chapter 1\n\nReadable text.\n\n*PDF pages 1–2*",
            )
        ],
    )

    result = generate_docusaurus_site(book, tmp_path / "site")

    index_doc = result.docs_dir / "01-chapter-1-aaaaaaaa.md"
    assert index_doc.exists()
    content = index_doc.read_text(encoding="utf-8")
    assert "slug: /" in content
    assert "toc_min_heading_level: 2" in content
    assert (result.site_dir / "sidebars.js").exists()
    assert (result.site_dir / "docusaurus.config.mjs").exists()
    assert (result.site_dir / "src/css/custom.css").exists()
    assert (result.site_dir / "src/pages/search.js").exists()
    assert (result.site_dir / "src/pages/quality-report.js").exists()
    assert (result.site_dir / "src/components/PdfCodeBlock.js").exists()
    assert (result.site_dir / "src/theme/MDXComponents.js").exists()
    assert (result.site_dir / "static/favicon.svg").exists()
    config = (result.site_dir / "docusaurus.config.mjs").read_text(encoding="utf-8")
    assert "favicon: 'favicon.svg'" in config
    assert "to: '/quality-report'" in config
    assert "/quality-report.html" not in config
    assert "className: 'booksite-book-title'" in config
    assert f"label: {json.dumps(book.title, ensure_ascii=True)}" in config
    css = (result.site_dir / "src/css/custom.css").read_text(encoding="utf-8")
    assert 'content: "On this page"' in css
    assert "border-left: 2px solid #d8e4ff" in css
    assert ".booksite-pdf-code" in css
    assert 'font-family: Consolas, "SFMono-Regular", Menlo, monospace' in css
    assert "overflow-x: auto" in css
    code_component = (
        result.site_dir / "src/components/PdfCodeBlock.js"
    ).read_text(encoding="utf-8")
    assert "JSON.parse(atob(data))" in code_component
    assert 'aria-label="Copy code"' in code_component
    assert "navigator.clipboard.writeText" in code_component
    mdx_components = (
        result.site_dir / "src/theme/MDXComponents.js"
    ).read_text(encoding="utf-8")
    assert "PdfCodeBlock" in mdx_components
    search_index = json.loads(
        (result.site_dir / "static/search-index.json").read_text(encoding="utf-8")
    )
    assert search_index[0]["title"] == "Chapter 1"
    assert search_index[0]["url"] == "/"
    assert "Readable text" in search_index[0]["text"]
    package = json.loads((result.site_dir / "package.json").read_text(encoding="utf-8"))
    assert "type" not in package
    assert "@docusaurus/faster" not in package["dependencies"]
    assert "@easyops-cn/docusaurus-search-local" not in package["dependencies"]
    assert package["scripts"]["build"] == "docusaurus build && python3 cleanup-build.py"
    assert (result.site_dir / "cleanup-build.py").exists()
    workspace_config = (result.site_dir / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert "autoInstallPeers: false" in workspace_config
    assert "'@swc/core': true" in workspace_config
    assert "core-js: true" in workspace_config
    search_page = (result.site_dir / "src/pages/search.js").read_text(encoding="utf-8")
    assert 'role="status"' in search_page
    assert 'aria-live="polite"' in search_page
    assert "Search index could not be loaded." in search_page

    preview_server = result.site_dir / "serve-local.py"
    preview_launcher = result.site_dir / "打开网站.command"
    preview_guide = result.site_dir / "本地打开说明.txt"
    assert preview_server.exists()
    assert preview_launcher.exists()
    assert preview_launcher.stat().st_mode & stat.S_IXUSR
    assert "serve-local.py" in preview_launcher.read_text(encoding="utf-8")
    assert "不要直接双击 build/index.html" in preview_guide.read_text(encoding="utf-8")

    build_dir = result.site_dir / "build"
    build_dir.mkdir()
    (build_dir / "index.html").write_text(
        "<!doctype html><title>Local preview works</title>",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [
            sys.executable,
            str(preview_server),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--no-open",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        output_line = process.stdout.readline().strip()
        assert output_line.startswith("本地网站：http://127.0.0.1:")
        preview_url = output_line.removeprefix("本地网站：")
        with urlopen(preview_url, timeout=3) as response:
            assert response.status == 200
            assert b"Local preview works" in response.read()
    finally:
        process.terminate()
        process.wait(timeout=3)
