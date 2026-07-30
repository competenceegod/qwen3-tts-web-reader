from booksite.assemble.native import _block_from_pdf, _escape_mdx, _section_markdown
from booksite.models.book_ir import (
    BlockIR,
    CodeLineIR,
    CodeSpanIR,
    CodeStyleIR,
    PageIR,
)
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
            },
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
        "    - Complete data control and privacy\n"
        "    - No API costs or usage limits\n"
        "- Advantages of cloud models:\n"
        "    - No hardware requirements"
    ) in markdown


def test_nested_bullets_under_ordered_item_use_commonmark_content_indent() -> None:
    page = PageIR(
        page_index=0,
        width=500,
        height=600,
        native_text="review question",
        native_text_char_count=15,
        blocks=[
            BlockIR(
                block_id="p0001-b001",
                page_index=0,
                order=0,
                type="list",
                bbox=(85.7, 100, 450, 115),
                text="1. Which options apply?",
                markdown="1. Which options apply?",
                source_engine="native",
            ),
            BlockIR(
                block_id="p0001-b002",
                page_index=0,
                order=1,
                type="list",
                bbox=(116.2, 120, 450, 135),
                text="• First choice",
                markdown="- First choice",
                source_engine="native",
            ),
            BlockIR(
                block_id="p0001-b003",
                page_index=0,
                order=2,
                type="list",
                bbox=(116.2, 140, 450, 155),
                text="• Second choice",
                markdown="- Second choice",
                source_engine="native",
            ),
        ],
        primary_engine="native",
        selected_engine="native",
        quality_score=1.0,
    )
    section = TocEntry(
        level=1,
        title="Review",
        start_page=1,
        end_page=1,
        source="pdf_bookmark",
        slug="review",
    )

    markdown = _section_markdown(section, [page], {1: []})

    assert ("1. Which options apply?\n    - First choice\n    - Second choice") in markdown


def test_list_continuation_removes_layout_only_hyphenation() -> None:
    raw_block = {
        "bbox": (85.0, 300.0, 470.0, 335.0),
        "lines": [
            {
                "bbox": (85.0, 300.0, 105.0, 315.0),
                "spans": [{"text": "10.", "font": "MinionPro-Regular", "size": 11.0}],
            },
            {
                "bbox": (110.0, 300.0, 470.0, 315.0),
                "spans": [
                    {
                        "text": "Compare the trade-offs be-",
                        "font": "MinionPro-Regular",
                        "size": 11.0,
                    }
                ],
            },
            {
                "bbox": (85.0, 320.0, 150.0, 335.0),
                "spans": [{"text": "tween them:", "font": "MinionPro-Regular", "size": 11.0}],
            },
        ],
    }

    block = _block_from_pdf(
        raw_block,
        page_index=88,
        order=17,
        repeated_marginals=set(),
        toc_titles={},
        typical_font_size=11.0,
        page_height=666.0,
    )

    assert block is not None
    assert block.markdown == "10. Compare the trade-offs between them:"


def test_styled_code_between_peer_list_items_preserves_list_context() -> None:
    code_style = CodeStyleIR(
        background_color="#fafafa",
        border_color="#e1e1e1",
        font_size_pt=9.0,
    )

    def list_block(order: int, x: float, markdown: str) -> BlockIR:
        return BlockIR(
            block_id=f"p0089-b{order + 1:03d}",
            page_index=88,
            order=order,
            type="list",
            bbox=(x, 400 + order * 20, 470, 415 + order * 20),
            text=markdown,
            markdown=markdown,
            source_engine="native",
        )

    def code_block(order: int, text: str) -> BlockIR:
        return BlockIR(
            block_id=f"p0089-b{order + 1:03d}",
            page_index=88,
            order=order,
            type="code",
            bbox=(148.5, 400 + order * 20, 430, 415 + order * 20),
            text=text,
            markdown=f"```text\n{text}\n```",
            code_lines=[
                CodeLineIR(
                    spans=[
                        CodeSpanIR(
                            text=text,
                            color="#383a42",
                            font_family="Consolas",
                            font_size_pt=9.0,
                        )
                    ]
                )
            ],
            code_style=code_style,
            source_engine="native",
        )

    page = PageIR(
        page_index=88,
        width=540,
        height=666,
        native_text="review approaches",
        native_text_char_count=17,
        blocks=[
            list_block(0, 85.7, "10. Compare the following approaches:"),
            list_block(1, 116.2, "- Approach A"),
            code_block(2, "from provider_a import ModelA"),
            list_block(3, 116.2, "- Approach B"),
            code_block(4, "from provider_b import ModelB"),
        ],
        primary_engine="native",
        selected_engine="native",
        quality_score=1.0,
    )
    section = TocEntry(
        level=1,
        title="Review",
        start_page=89,
        end_page=89,
        source="pdf_bookmark",
        slug="review",
    )

    markdown = _section_markdown(section, [page] * 89, {89: []})
    component_lines = [line for line in markdown.splitlines() if "<PdfCodeBlock" in line]

    assert "    - Approach A" in markdown
    assert "    - Approach B" in markdown
    assert len(component_lines) == 2
    assert all(line.startswith("        <PdfCodeBlock") for line in component_lines)


def test_paragraphs_starting_with_mdx_module_keywords_remain_literal_text() -> None:
    assert _escape_mdx("import os") == "import&#32;os"
    assert (
        _escape_mdx("export OPENAI_API_KEY=<your token>")
        == "export&#32;OPENAI\\_API\\_KEY=&lt;your token&gt;"
    )


def test_mdx_brace_entities_render_as_braces_instead_of_literal_entity_text() -> None:
    assert _escape_mdx('{"topic": "a rainy day"}') == ('&#123;"topic": "a rainy day"&#125;')
