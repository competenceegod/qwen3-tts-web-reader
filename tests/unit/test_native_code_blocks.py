from booksite.assemble.native import _block_from_pdf, _section_markdown
from booksite.models.book_ir import BlockIR, PageIR
from booksite.models.reports import TocEntry


def test_short_monospace_delimiters_are_classified_as_code() -> None:
    raw_block = {
        "bbox": (85.5, 155.8, 135.0, 167.7),
        "lines": [
            {
                "bbox": (85.5, 155.8, 135.0, 167.7),
                "spans": [
                    {
                        "text": "      }])]",
                        "font": "Consolas",
                        "size": 9.0,
                    }
                ],
            }
        ],
    }

    block = _block_from_pdf(
        raw_block,
        page_index=85,
        order=7,
        repeated_marginals=set(),
        toc_titles={},
        typical_font_size=10.0,
        page_height=648.0,
    )

    assert block is not None
    assert block.type == "code"
    assert block.markdown == "```text\n      }])]\n```"


def test_short_monospace_operator_chain_is_classified_as_code() -> None:
    raw_block = {
        "bbox": (85.5, 155.8, 135.0, 167.7),
        "lines": [
            {
                "bbox": (85.5, 155.8, 135.0, 167.7),
                "spans": [
                    {
                        "text": "    } |",
                        "font": "Consolas",
                        "size": 9.0,
                    }
                ],
            }
        ],
    }

    block = _block_from_pdf(
        raw_block,
        page_index=71,
        order=11,
        repeated_marginals=set(),
        toc_titles={},
        typical_font_size=10.0,
        page_height=648.0,
    )

    assert block is not None
    assert block.type == "code"
    assert block.markdown == "```text\n    } |\n```"


def test_code_blocks_preserve_blank_lines_from_vertical_gap() -> None:
    page = PageIR(
        page_index=0,
        width=500,
        height=600,
        native_text="code",
        native_text_char_count=4,
        blocks=[
            BlockIR(
                block_id="p0001-b001",
                page_index=0,
                order=0,
                type="code",
                bbox=(85.5, 332.5, 323.0, 358.9),
                text="from first import One\nfrom second import Two",
                markdown="```text\nfrom first import One\nfrom second import Two\n```",
                source_engine="native",
            ),
            BlockIR(
                block_id="p0001-b002",
                page_index=0,
                order=1,
                type="code",
                bbox=(85.5, 376.0, 362.6, 402.3),
                text="def example():\n    chat = object()",
                markdown="```text\ndef example():\n    chat = object()\n```",
                source_engine="native",
            ),
            BlockIR(
                block_id="p0001-b003",
                page_index=0,
                order=2,
                type="code",
                bbox=(85.5, 419.5, 372.5, 445.8),
                text="    message = object()",
                markdown="```text\n    message = object()\n```",
                source_engine="native",
            ),
        ],
        primary_engine="native",
        selected_engine="native",
        quality_score=1.0,
    )
    section = TocEntry(
        level=1,
        title="Code Chapter",
        start_page=1,
        end_page=1,
        source="pdf_bookmark",
        slug="code-chapter",
    )

    markdown = _section_markdown(section, [page], {1: []})

    assert "from second import Two\n\ndef example():" in markdown
    assert "    chat = object()\n\n    message = object()" in markdown
