import base64
import json

import pytest
from pydantic import ValidationError

from booksite.assemble.native import (
    _block_from_pdf,
    _bounded_float,
    _code_style_for_bbox,
    _section_markdown,
)
from booksite.models.book_ir import (
    BlockIR,
    CodeLineIR,
    CodeSpanIR,
    CodeStyleIR,
    PageIR,
)
from booksite.models.reports import TocEntry


def test_code_block_preserves_pdf_span_styles() -> None:
    raw_block = {
        "bbox": (85.5, 100.0, 300.0, 112.0),
        "lines": [
            {
                "bbox": (85.5, 100.0, 300.0, 112.0),
                "spans": [
                    {
                        "text": "class ",
                        "font": "Consolas-Bold",
                        "size": 9.0,
                        "flags": 16,
                        "color": 0xA626A4,
                    },
                    {
                        "text": "from ",
                        "font": "Consolas",
                        "size": 9.0,
                        "flags": 8,
                        "color": 0xA626A4,
                    },
                    {
                        "text": "package ",
                        "font": "Consolas",
                        "size": 9.0,
                        "flags": 8,
                        "color": 0x383A42,
                    },
                    {
                        "text": '"example"',
                        "font": "Consolas-Italic",
                        "size": 9.0,
                        "flags": 10,
                        "color": 0x50A14F,
                    },
                ],
            }
        ],
    }
    style = CodeStyleIR(
        background_color="#fafafa",
        border_color="#e1e1e1",
        font_size_pt=9.0,
    )

    block = _block_from_pdf(
        raw_block,
        page_index=0,
        order=0,
        repeated_marginals=set(),
        toc_titles={},
        typical_font_size=11.0,
        page_height=666.0,
        code_style=style,
    )

    assert block is not None
    assert block.code_style == style
    assert block.code_lines[0].spans == [
        CodeSpanIR(
            text="class ",
            color="#a626a4",
            font_family="Consolas-Bold",
            font_size_pt=9.0,
            bold=True,
        ),
        CodeSpanIR(
            text="from ",
            color="#a626a4",
            font_family="Consolas",
            font_size_pt=9.0,
        ),
        CodeSpanIR(
            text="package ",
            color="#383a42",
            font_family="Consolas",
            font_size_pt=9.0,
        ),
        CodeSpanIR(
            text='"example"',
            color="#50a14f",
            font_family="Consolas-Italic",
            font_size_pt=9.0,
            italic=True,
        ),
    ]


@pytest.mark.parametrize("font_size", [float("inf"), 1e100])
def test_code_style_models_reject_non_renderable_font_sizes(font_size: float) -> None:
    with pytest.raises(ValidationError):
        CodeSpanIR(
            text="unsafe",
            color="#000000",
            font_family="Consolas",
            font_size_pt=font_size,
        )

    with pytest.raises(ValidationError):
        CodeStyleIR(
            background_color="#ffffff",
            border_color="#000000",
            font_size_pt=font_size,
        )


def test_code_span_model_rejects_unbounded_font_family() -> None:
    with pytest.raises(ValidationError):
        CodeSpanIR(
            text="unsafe",
            color="#000000",
            font_family="x" * 257,
            font_size_pt=9.0,
        )


def test_pdf_numeric_sanitizer_handles_integer_overflow() -> None:
    assert _bounded_float(10**10000, 9.0) == 9.0


def test_pdf_code_span_values_are_safely_bounded() -> None:
    raw_block = {
        "bbox": (85.5, 100.0, 300.0, 112.0),
        "lines": [
            {
                "bbox": (85.5, 100.0, 300.0, 112.0),
                "spans": [
                    {
                        "text": "safe_value",
                        "font": "Consolas" + ("A" * 300),
                        "size": float("inf"),
                        "flags": "not-an-int",
                        "color": float("inf"),
                    }
                ],
            }
        ],
    }

    block = _block_from_pdf(
        raw_block,
        page_index=0,
        order=0,
        repeated_marginals=set(),
        toc_titles={},
        typical_font_size=11.0,
        page_height=666.0,
    )

    assert block is not None
    assert block.code_lines[0].spans[0].font_size_pt == 9.0
    assert len(block.code_lines[0].spans[0].font_family) == 256
    assert block.code_lines[0].spans[0].color == "#000000"


def test_code_surface_uses_containing_pdf_fill_and_accent_rule() -> None:
    drawings = [
        {
            "rect": (72.0, 95.8, 468.0, 200.7),
            "fill": (0.98, 0.98, 0.98),
            "color": None,
            "width": None,
        },
        {
            "rect": (73.5, 95.8, 73.5, 200.7),
            "fill": None,
            "color": (0.882, 0.882, 0.882),
            "width": 3.0,
        },
    ]

    style = _code_style_for_bbox(drawings, (85.5, 100.0, 300.0, 112.0), 9.0)

    assert style == CodeStyleIR(
        background_color="#fafafa",
        border_color="#e1e1e1",
        font_size_pt=9.0,
    )


def test_adjacent_styled_code_serializes_as_one_pdf_code_component() -> None:
    style = CodeStyleIR(
        background_color="#282a36",
        border_color="#44475a",
        font_size_pt=9.0,
    )
    blocks = [
        BlockIR(
            block_id="p0001-b001",
            page_index=0,
            order=0,
            type="code",
            bbox=(85.5, 100.0, 300.0, 112.0),
            text="from package import value",
            markdown="```text\nfrom package import value\n```",
            code_lines=[
                CodeLineIR(
                    spans=[
                        CodeSpanIR(
                            text="from",
                            color="#a626a4",
                            font_family="Consolas",
                            font_size_pt=9.0,
                        )
                    ]
                )
            ],
            code_style=style,
            source_engine="native",
        ),
        BlockIR(
            block_id="p0001-b002",
            page_index=0,
            order=1,
            type="code",
            bbox=(85.5, 130.0, 300.0, 142.0),
            text='value = "green"',
            markdown='```text\nvalue = "green"\n```',
            code_lines=[
                CodeLineIR(
                    spans=[
                        CodeSpanIR(
                            text='"green"',
                            color="#50a14f",
                            font_family="Consolas",
                            font_size_pt=9.0,
                        )
                    ]
                )
            ],
            code_style=style,
            source_engine="native",
        ),
    ]
    page = PageIR(
        page_index=0,
        width=500,
        height=600,
        native_text="code",
        native_text_char_count=4,
        blocks=blocks,
        primary_engine="native",
        selected_engine="native",
        quality_score=1.0,
    )
    section = TocEntry(
        level=1,
        title="Styled code",
        start_page=1,
        end_page=1,
        source="pdf_bookmark",
        slug="styled-code",
    )

    markdown = _section_markdown(section, [page], {1: []})

    assert markdown.count('<PdfCodeBlock data="') == 1
    encoded = markdown.split('<PdfCodeBlock data="', 1)[1].split('" />', 1)[0]
    payload = json.loads(base64.b64decode(encoded))
    assert payload["backgroundColor"] == "#282a36"
    assert payload["lines"][0][0]["color"] == "#a626a4"
    assert payload["lines"][1] == []
    assert payload["lines"][2][0]["color"] == "#50a14f"
