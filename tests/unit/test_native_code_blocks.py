from booksite.assemble.native import _block_from_pdf


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
    assert block.markdown == "```text\n}])]\n```"
