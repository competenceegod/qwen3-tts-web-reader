import re
from pathlib import Path

import pymupdf

from booksite.pdf.audit import audit_pdf
from booksite.quality.rules import NativeTextStatus


def test_audit_preserves_pages_metadata_and_in_range_bookmarks(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    document = pymupdf.open()
    for page_number in range(3):
        page = document.new_page(width=400, height=600)
        page.insert_text((30, 30), "Sample Book", fontsize=9)
        page.insert_text((30, 90), f"Chapter {page_number + 1}", fontsize=22)
        page.insert_text(
            (30, 140),
            ("This is a native text paragraph for audit validation. " * 4),
            fontsize=11,
        )
        page.insert_text((195, 570), str(page_number + 1), fontsize=9)
    document.set_toc([[1, "Chapter 1", 1], [1, "Chapter 2", 2], [1, "Chapter 3", 3]])
    document.save(pdf_path)
    document.close()

    report = audit_pdf(pdf_path, max_pages=2)

    assert report.page_count == 2
    assert report.total_page_count == 3
    assert [entry.title for entry in report.original_toc] == ["Chapter 1", "Chapter 2"]
    assert all(page.native_text_status is NativeTextStatus.TEXT_GOOD for page in report.pages)
    assert report.pages[0].native_text.startswith("Sample Book")


def test_audit_creates_url_safe_book_id_for_non_ascii_filename(tmp_path: Path) -> None:
    pdf_path = tmp_path / "书籍 # One.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((30, 80), "Readable content. " * 10)
    document.save(pdf_path)
    document.close()

    report = audit_pdf(pdf_path)

    assert re.fullmatch(r"one-[0-9a-f]{8}", report.book_id)
