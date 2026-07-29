import json
from pathlib import Path

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
    config = (result.site_dir / "docusaurus.config.mjs").read_text(encoding="utf-8")
    assert "to: '/quality-report'" in config
    assert "/quality-report.html" not in config
    assert "className: 'booksite-book-title'" in config
    assert f"label: {json.dumps(book.title, ensure_ascii=True)}" in config
    css = (result.site_dir / "src/css/custom.css").read_text(encoding="utf-8")
    assert 'content: "On this page"' in css
    assert "border-left: 2px solid #d8e4ff" in css
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
    workspace_config = (result.site_dir / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert "autoInstallPeers: false" in workspace_config
    assert "'@swc/core': true" in workspace_config
    assert "core-js: true" in workspace_config
