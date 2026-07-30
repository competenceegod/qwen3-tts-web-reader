from booksite.assemble.native import _block_from_pdf


def test_marginal_header_is_removed_when_paired_with_page_number() -> None:
    raw_block = {
        "bbox": (71.4, 35.8, 467.5, 47.7),
        "lines": [
            {
                "bbox": (371.4, 35.8, 467.5, 47.6),
                "spans": [
                    {
                        "text": "First Steps with LangChain",
                        "font": "CrimsonPro-Italic",
                        "size": 9.0,
                    }
                ],
            },
            {
                "bbox": (71.4, 35.9, 81.4, 47.7),
                "spans": [
                    {
                        "text": "48",
                        "font": "CrimsonPro-Regular",
                        "size": 9.0,
                    }
                ],
            },
        ],
    }

    block = _block_from_pdf(
        raw_block,
        page_index=72,
        order=0,
        repeated_marginals=set(),
        toc_titles={},
        typical_font_size=11.0,
        page_height=666.0,
    )

    assert block is None
