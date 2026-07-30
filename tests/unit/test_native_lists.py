from booksite.assemble.native import _block_from_pdf, _section_markdown
from booksite.models.book_ir import BlockIR, PageIR
from booksite.models.reports import TocEntry


def test_pdf_bullet_glyph_is_emitted_as_semantic_markdown() -> None:
    raw_block = {
        "bbox": (54.0, 300.0, 420.0, 315.0),
        "lines": [
            {
                "bbox": (54.0, 300.0, 60.0, 315.0),
                "spans": [
                    {
                        "text": "•",
                        "font": "MinionPro-Regular",
                        "size": 11.0,
                    }
                ],
            },
            {
                "bbox": (74.0, 300.0, 420.0, 315.0),
                "spans": [
                    {
                        "text": "Track the provenance of generated content",
                        "font": "MinionPro-Regular",
                        "size": 11.0,
                    }
                ],
            }
        ],
    }

    block = _block_from_pdf(
        raw_block,
        page_index=65,
        order=4,
        repeated_marginals=set(),
        toc_titles={},
        typical_font_size=11.0,
        page_height=648.0,
    )

    assert block is not None
    assert block.type == "list"
    assert block.markdown == "- Track the provenance of generated content"


def test_adjacent_list_blocks_remain_one_markdown_list() -> None:
    page = PageIR(
        page_index=0,
        width=500,
        height=600,
        native_text="• First item\n• Second item",
        native_text_char_count=26,
        blocks=[
            BlockIR(
                block_id="p0001-b001",
                page_index=0,
                order=0,
                type="list",
                text="• First item",
                markdown="- First item",
                source_engine="native",
            ),
            BlockIR(
                block_id="p0001-b002",
                page_index=0,
                order=1,
                type="list",
                text="• Second item",
                markdown="- Second item",
                source_engine="native",
            ),
        ],
        primary_engine="native",
        selected_engine="native",
        quality_score=1.0,
    )
    section = TocEntry(
        level=1,
        title="List Chapter",
        start_page=1,
        end_page=1,
        source="pdf_bookmark",
        slug="list-chapter",
    )

    markdown = _section_markdown(section, [page], {1: []})

    assert "- First item\n- Second item" in markdown
    assert "- First item\n\n- Second item" not in markdown
