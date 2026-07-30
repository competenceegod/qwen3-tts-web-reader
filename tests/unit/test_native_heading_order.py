from booksite.assemble.native import _section_markdown
from booksite.models.book_ir import BlockIR, PageIR
from booksite.models.reports import TocEntry


def test_nested_heading_stays_at_its_pdf_block_position() -> None:
    page = PageIR(
        page_index=0,
        width=500,
        height=600,
        native_text="body before heading",
        native_text_char_count=19,
        blocks=[
            BlockIR(
                block_id="p0001-b001",
                page_index=0,
                order=0,
                type="paragraph",
                bbox=(72, 62, 400, 75),
                text="Text before the nested heading.",
                markdown="Text before the nested heading.",
                source_engine="native",
            ),
            BlockIR(
                block_id="p0001-b002",
                page_index=0,
                order=1,
                type="title",
                bbox=(72, 273, 230, 296),
                text="Running local models",
                markdown="## Running local models",
                heading_level=2,
                source_engine="native",
            ),
            BlockIR(
                block_id="p0001-b003",
                page_index=0,
                order=2,
                type="paragraph",
                bbox=(72, 297, 470, 310),
                text="Text after the nested heading.",
                markdown="Text after the nested heading.",
                source_engine="native",
            ),
        ],
        primary_engine="native",
        selected_engine="native",
        quality_score=1.0,
    )
    section = TocEntry(
        level=1,
        title="Chapter 2",
        start_page=1,
        end_page=1,
        source="pdf_bookmark",
        slug="chapter-2",
    )
    nested = TocEntry(
        level=2,
        title="Running local models",
        start_page=1,
        end_page=1,
        source="pdf_bookmark",
        slug="running-local-models",
    )

    markdown = _section_markdown(section, [page], {1: [section, nested]})

    assert markdown.index("Text before") < markdown.index("## Running local models")
    assert markdown.index("## Running local models") < markdown.index("Text after")
    assert markdown.count("## Running local models") == 1
