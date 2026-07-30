import base64
import json
from pathlib import Path

import pymupdf

from booksite.assemble.native import assemble_native_book
from booksite.pdf.audit import audit_pdf


def _styled_code_payload(markdown: str) -> dict[str, object]:
    encoded = markdown.split('<PdfCodeBlock data="', 1)[1].split('" />', 1)[0]
    return json.loads(base64.b64decode(encoded))


def test_native_assembly_uses_bookmarks_and_removes_repeated_marginals(tmp_path: Path) -> None:
    pdf_path = tmp_path / "book.pdf"
    document = pymupdf.open()
    for index in range(4):
        page = document.new_page(width=400, height=600)
        page.insert_text((30, 30), "Running Header", fontsize=9)
        if index in {0, 2}:
            page.insert_text((30, 95), f"Chapter {index // 2 + 1}", fontsize=22)
        page.insert_text(
            (30, 145),
            f"Page {index + 1} body text. " + ("Readable native content. " * 8),
            fontsize=11,
        )
        page.insert_text((195, 570), str(index + 1), fontsize=9)
    document.set_toc([[1, "Chapter 1", 1], [1, "Chapter 2", 3]])
    document.save(pdf_path)
    document.close()

    audit = audit_pdf(pdf_path)
    book = assemble_native_book(pdf_path, audit)

    assert [section.title for section in book.sections] == ["Chapter 1", "Chapter 2"]
    assert book.sections[0].source_pages == [1, 2]
    assert "Running Header" not in book.sections[0].markdown
    assert "PDF pages 1–2" in book.sections[0].markdown
    assert len(book.pages) == 4


def test_native_assembly_merges_adjacent_monospace_blocks(tmp_path: Path) -> None:
    pdf_path = tmp_path / "code-book.pdf"
    document = pymupdf.open()
    page = document.new_page(width=400, height=600)
    page.insert_text((30, 70), "Code Chapter", fontsize=22)
    page.insert_text((30, 130), "from pathlib import Path", fontsize=10, fontname="cour")
    page.insert_text((30, 150), "source = Path('book.pdf')", fontsize=10, fontname="cour")
    page.insert_text((30, 170), "print(source.name)", fontsize=10, fontname="cour")
    document.set_toc([[1, "Code Chapter", 1]])
    document.save(pdf_path)
    document.close()

    book = assemble_native_book(pdf_path, audit_pdf(pdf_path))
    markdown = book.sections[0].markdown
    payload = _styled_code_payload(markdown)
    code_text = "\n".join("".join(span["text"] for span in line) for line in payload["lines"])

    assert markdown.count('<PdfCodeBlock data="') == 1
    assert "from pathlib import Path\nsource = Path('book.pdf')\nprint(source.name)" in code_text


def test_native_assembly_keeps_short_monospace_delimiters_in_code(tmp_path: Path) -> None:
    pdf_path = tmp_path / "code-delimiters.pdf"
    document = pymupdf.open()
    page = document.new_page(width=500, height=600)
    page.insert_text((30, 70), "Code Chapter", fontsize=22)
    code_lines = [
        "prompt = ChatPromptTemplate.from_messages(",
        '    [{"type": "image_url"},',
        "    } |",
        "    }])]",
        ")",
        'prompt.invoke({"image_bytes_str": "test-url"})',
    ]
    for line_number, line in enumerate(code_lines):
        page.insert_text(
            (30, 130 + line_number * 15),
            line,
            fontsize=10,
            fontname="cour",
        )
    document.set_toc([[1, "Code Chapter", 1]])
    document.save(pdf_path)
    document.close()

    book = assemble_native_book(pdf_path, audit_pdf(pdf_path))
    markdown = book.sections[0].markdown
    payload = _styled_code_payload(markdown)
    code_text = "\n".join("".join(span["text"] for span in line) for line in payload["lines"])

    assert markdown.count('<PdfCodeBlock data="') == 1
    assert "\n    } |\n" in code_text
    assert "\n    }])]\n)\nprompt.invoke" in code_text
    assert "&#125;" not in code_text


def test_native_assembly_promotes_one_shaded_surface_as_one_code_block(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "shaded-code.pdf"
    document = pymupdf.open()
    page = document.new_page(width=500, height=600)
    page.insert_text((30, 70), "Code Chapter", fontsize=22)
    page.draw_rect(
        pymupdf.Rect(30, 105, 470, 230),
        color=None,
        fill=(0.98, 0.98, 0.98),
    )
    code_lines = [
        "prompt = make_prompt(",
        '[("user",',
        '[{"type": "image_url",',
        '"image_url": {"url": source_url},',
        ")]",
        'image_url = "https://example.com/image.png"',
    ]
    for line_number, line in enumerate(code_lines):
        page.insert_text(
            (45, 125 + line_number * 16),
            line,
            fontsize=10,
            fontname="helv",
        )
    document.set_toc([[1, "Code Chapter", 1]])
    document.save(pdf_path)
    document.close()

    book = assemble_native_book(pdf_path, audit_pdf(pdf_path))
    markdown = book.sections[0].markdown
    payload = _styled_code_payload(markdown)
    code_text = "\n".join("".join(span["text"] for span in line) for line in payload["lines"])

    assert markdown.count('<PdfCodeBlock data="') == 1
    assert code_text == "\n".join(code_lines)
    assert "&#123;" not in markdown


def test_native_assembly_promotes_dark_terminal_surfaces_without_syntax_anchors(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "dark-terminal.pdf"
    document = pymupdf.open()
    page = document.new_page(width=500, height=600)
    page.insert_text((30, 70), "Terminal Chapter", fontsize=22)
    page.draw_rect(
        pymupdf.Rect(30, 105, 470, 165),
        color=(0.27, 0.28, 0.35),
        fill=(0.16, 0.16, 0.21),
    )
    terminal_lines = [
        "ollama pull deepseek-r1:1.5b",
        "ollama serve",
    ]
    for line_number, line in enumerate(terminal_lines):
        page.insert_text(
            (45, 128 + line_number * 18),
            line,
            fontsize=10,
            fontname="helv",
            color=(0.97, 0.97, 0.97),
        )
    document.set_toc([[1, "Terminal Chapter", 1]])
    document.save(pdf_path)
    document.close()

    book = assemble_native_book(pdf_path, audit_pdf(pdf_path))
    markdown = book.sections[0].markdown
    payload = _styled_code_payload(markdown)
    code_text = "\n".join("".join(span["text"] for span in line) for line in payload["lines"])

    assert markdown.count('<PdfCodeBlock data="') == 1
    assert code_text == "\n".join(terminal_lines)
    assert payload["backgroundColor"] == "#292936"
    assert payload["borderColor"] == "#454759"


def test_native_assembly_ignores_large_page_background_as_code_surface(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "large-background.pdf"
    document = pymupdf.open()
    page = document.new_page(width=500, height=600)
    page.draw_rect(
        pymupdf.Rect(25, 50, 475, 500),
        color=None,
        fill=(0.96, 0.96, 0.96),
    )
    page.insert_text((45, 80), "Background Chapter", fontsize=22)
    page.insert_text(
        (45, 130),
        "return to the main discussion after this explanatory note",
        fontsize=11,
        fontname="helv",
    )
    document.set_toc([[1, "Background Chapter", 1]])
    document.save(pdf_path)
    document.close()

    book = assemble_native_book(pdf_path, audit_pdf(pdf_path))
    markdown = book.sections[0].markdown

    assert '<PdfCodeBlock data="' not in markdown
    assert "return to the main discussion after this explanatory note" in markdown


def test_native_assembly_does_not_promote_arbitrary_dark_callout(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "dark-callout.pdf"
    document = pymupdf.open()
    page = document.new_page(width=500, height=600)
    page.insert_text((30, 70), "Callout Chapter", fontsize=22)
    page.draw_rect(
        pymupdf.Rect(30, 105, 470, 165),
        color=(0.22, 0.3, 0.42),
        fill=(0.1, 0.15, 0.25),
    )
    page.insert_text(
        (45, 132),
        "Important: this section explains the model.",
        fontsize=11,
        fontname="helv",
        color=(0.97, 0.97, 0.97),
    )
    document.set_toc([[1, "Callout Chapter", 1]])
    document.save(pdf_path)
    document.close()

    book = assemble_native_book(pdf_path, audit_pdf(pdf_path))
    markdown = book.sections[0].markdown

    assert '<PdfCodeBlock data="' not in markdown
    assert "Important: this section explains the model." in markdown


def test_native_assembly_covers_pages_before_first_bookmark(tmp_path: Path) -> None:
    pdf_path = tmp_path / "front-matter.pdf"
    document = pymupdf.open()
    for page_number in (1, 2):
        page = document.new_page(width=400, height=600)
        page.insert_text(
            (30, 100),
            "Cover page" if page_number == 1 else "Chapter One",
            fontsize=22,
        )
        page.insert_text((30, 150), "Readable native text. " * 8, fontsize=11)
    document.set_toc([[1, "Chapter One", 2]])
    document.save(pdf_path)
    document.close()

    book = assemble_native_book(pdf_path, audit_pdf(pdf_path))

    assert [section.title for section in book.sections] == ["Front Matter", "Chapter One"]
    assert book.sections[0].source_pages == [1]
    assert {page for section in book.sections for page in section.source_pages} == {1, 2}
