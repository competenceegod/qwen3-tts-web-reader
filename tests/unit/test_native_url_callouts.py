import base64
import json

from booksite.assemble.native import _block_from_pdf, _merge_pdf_url_callouts
from booksite.models.book_ir import BlockIR, CodeStyleIR


def _block(
    order: int,
    block_type: str,
    x: float,
    y: float,
    text: str,
    *,
    style: CodeStyleIR | None = None,
) -> BlockIR:
    return BlockIR(
        block_id=f"p0093-b{order + 1:03d}",
        page_index=92,
        order=order,
        type=block_type,
        bbox=(x, y, 470.0, y + 12.4),
        text=text,
        markdown=text,
        code_style=style,
        source_engine="native",
    )


def _callout_payload(markdown: str) -> dict[str, object]:
    encoded = markdown.split('<PdfUrlCallout data="', 1)[1].split('" />', 1)[0]
    return json.loads(base64.b64decode(encoded))


def test_merges_dehyphenated_prose_and_split_url_into_one_callout() -> None:
    style = CodeStyleIR(
        background_color="#f1f1f1",
        border_color="#d8dee9",
        font_size_pt=9.5,
    )
    blocks = [
        _block(
            1,
            "paragraph",
            130.26,
            74.25,
            (
                "As always, you can find all the code samples on our public GitHub "
                "repository as Jupy-"
            ),
        ),
        _block(
            2,
            "paragraph",
            130.98,
            88.75,
            ("ter notebooks: https://github.com/benman1/generative_ai_with_langchain/"),
            style=style,
        ),
        _block(
            3,
            "paragraph",
            130.59,
            103.25,
            "tree/second_edition/chapter3.",
            style=style,
        ),
    ]

    merged = _merge_pdf_url_callouts(blocks)

    assert len(merged) == 1
    assert merged[0].type == "paragraph"
    assert merged[0].markdown is not None
    payload = _callout_payload(merged[0].markdown)
    assert payload == {
        "prefix": (
            "As always, you can find all the code samples on our public GitHub "
            "repository as Jupyter notebooks: "
        ),
        "url": (
            "https://github.com/benman1/generative_ai_with_langchain/tree/second_edition/chapter3"
        ),
        "suffix": ".",
        "backgroundColor": "#f1f1f1",
        "borderColor": "#d8dee9",
    }
    assert "Jupy-" not in merged[0].text


def test_does_not_merge_unrelated_paragraph_and_code_blocks() -> None:
    style = CodeStyleIR(
        background_color="#fafafa",
        border_color="#e1e1e1",
        font_size_pt=9.0,
    )
    blocks = [
        _block(1, "paragraph", 85.0, 100.0, "Run this example:"),
        _block(2, "code", 116.0, 130.0, "https://example.com/base/", style=style),
        _block(3, "code", 116.0, 145.0, "print('done')", style=style),
    ]

    assert _merge_pdf_url_callouts(blocks) == blocks


def test_does_not_merge_url_tail_from_a_different_surface() -> None:
    style = CodeStyleIR(
        background_color="#f1f1f1",
        border_color="#d8dee9",
        font_size_pt=9.5,
    )
    blocks = [
        _block(1, "paragraph", 130.2, 74.2, "Read the Jupy-"),
        _block(
            2,
            "paragraph",
            130.9,
            88.7,
            "ter docs: https://example.com/project/",
            style=style,
        ),
        _block(3, "paragraph", 130.5, 103.2, "unrelated.", style=None),
    ]

    assert _merge_pdf_url_callouts(blocks) == blocks


def test_shaded_python_with_obfuscated_font_name_is_still_code() -> None:
    style = CodeStyleIR(
        background_color="#fafafa",
        border_color="#e1e1e1",
        font_size_pt=9.0,
    )
    raw_block = {
        "bbox": (148.5, 468.0, 381.0, 494.5),
        "lines": [
            {
                "bbox": (148.5, 468.0, 341.5, 480.0),
                "spans": [
                    {
                        "text": "from langchain_openai import ChatOpenAI",
                        "font": "font00000000301af5e8",
                        "size": 9.0,
                    }
                ],
            },
            {
                "bbox": (148.5, 482.5, 381.0, 494.5),
                "spans": [
                    {
                        "text": ('response = requests.get("https://example.com/model.json")'),
                        "font": "font00000000301af5e8",
                        "size": 9.0,
                    }
                ],
            },
        ],
    }

    block = _block_from_pdf(
        raw_block,
        page_index=88,
        order=19,
        repeated_marginals=set(),
        toc_titles={},
        typical_font_size=10.0,
        page_height=666.0,
        code_style=style,
    )

    assert block is not None
    assert block.type == "code"
    assert len(block.code_lines) == 2
    assert block.code_style == style


def test_shaded_prose_with_url_is_not_promoted_to_code() -> None:
    style = CodeStyleIR(
        background_color="#f1f1f1",
        border_color="#d8dee9",
        font_size_pt=9.5,
    )
    raw_block = {
        "bbox": (130.9, 89.4, 457.6, 100.7),
        "lines": [
            {
                "bbox": (130.9, 89.4, 457.6, 100.7),
                "spans": [
                    {
                        "text": ("ter notebooks: https://github.com/example/project/"),
                        "font": "font00000000301af5e8",
                        "size": 9.5,
                    }
                ],
            }
        ],
    }

    block = _block_from_pdf(
        raw_block,
        page_index=92,
        order=2,
        repeated_marginals=set(),
        toc_titles={},
        typical_font_size=10.0,
        page_height=666.0,
        code_style=style,
    )

    assert block is not None
    assert block.type == "paragraph"
