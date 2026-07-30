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


def test_adjacent_list_blocks_preserve_pdf_nesting_from_horizontal_position() -> None:
    def list_block(order: int, x: float, text: str) -> BlockIR:
        return BlockIR(
            block_id=f"p0001-b{order + 1:03d}",
            page_index=0,
            order=order,
            type="list",
            bbox=(x, 100 + order * 20, 400, 115 + order * 20),
            text=f"• {text}",
            markdown=f"- {text}",
            source_engine="native",
        )

    page = PageIR(
        page_index=0,
        width=500,
        height=600,
        native_text="nested list",
        native_text_char_count=11,
        blocks=[
            list_block(0, 84.7, "Advantages of local models:"),
            list_block(1, 116.2, "Complete data control and privacy"),
            list_block(2, 116.2, "No API costs or usage limits"),
            list_block(3, 84.7, "Advantages of cloud models:"),
            list_block(4, 116.2, "No hardware requirements"),
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

    assert (
        "- Advantages of local models:\n"
        "  - Complete data control and privacy\n"
        "  - No API costs or usage limits\n"
        "- Advantages of cloud models:\n"
        "  - No hardware requirements"
    ) in markdown
