from booksite.assemble.native import _block_from_pdf


def test_pdf_text_cannot_inject_remote_markdown_image() -> None:
    raw_block = {
        "bbox": (54.0, 200.0, 420.0, 215.0),
        "lines": [
            {
                "bbox": (54.0, 200.0, 420.0, 215.0),
                "spans": [
                    {
                        "text": "Do not load ![pixel](https://example.invalid/p.gif)",
                        "font": "MinionPro-Regular",
                        "size": 11.0,
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
        page_height=648.0,
    )

    assert block is not None
    assert "![pixel](https://" not in (block.markdown or "")
    assert r"\!\[pixel\]\(https://example.invalid/p.gif\)" in (block.markdown or "")
