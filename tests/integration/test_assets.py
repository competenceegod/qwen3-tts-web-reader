from pathlib import Path

import pymupdf

from booksite.assemble.native import assemble_native_book
from booksite.pdf.audit import audit_pdf
from booksite.site.assets import extract_native_assets


def test_repeated_image_is_referenced_on_every_source_page(tmp_path: Path) -> None:
    image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 16, 16), False)
    image.clear_with(0x1463FF)
    image_bytes = image.tobytes("png")

    pdf_path = tmp_path / "repeated-image.pdf"
    document = pymupdf.open()
    for page_number in (1, 2):
        page = document.new_page(width=400, height=600)
        page.insert_text((30, 70), f"Chapter {page_number}", fontsize=22)
        page.insert_text((30, 120), "Readable native text. " * 8, fontsize=11)
        page.insert_image(pymupdf.Rect(30, 200, 130, 300), stream=image_bytes)
    document.set_toc([[1, "Chapter 1", 1], [1, "Chapter 2", 2]])
    document.save(pdf_path)
    document.close()

    book = assemble_native_book(pdf_path, audit_pdf(pdf_path))
    previous_root = tmp_path / "static" / "assets" / "previous-deadbeef"
    previous_root.mkdir(parents=True)
    (previous_root / ".booksite-generated").write_text("old\n", encoding="utf-8")
    (previous_root / "old.png").write_bytes(image_bytes)
    assets = extract_native_assets(pdf_path, book, tmp_path / "static")

    assert not previous_root.exists()
    assert len(assets) == 2
    assert len({asset.path for asset in assets}) == 1
    assert "Figure from PDF page 1" in book.sections[0].markdown
    assert "Figure from PDF page 2" in book.sections[1].markdown
