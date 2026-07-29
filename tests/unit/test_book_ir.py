import pytest
from pydantic import ValidationError

from booksite.models.book_ir import BlockIR, PageIR


def test_page_ir_rejects_out_of_range_quality_score() -> None:
    with pytest.raises(ValidationError):
        PageIR(
            page_index=0,
            width=400,
            height=600,
            native_text="text",
            native_text_char_count=4,
            blocks=[],
            primary_engine="native",
            selected_engine="native",
            quality_score=1.1,
        )


def test_block_ir_requires_heading_level_only_for_titles() -> None:
    title = BlockIR(
        block_id="p0001-b001",
        page_index=0,
        order=0,
        type="title",
        text="Introduction",
        heading_level=1,
        source_engine="native",
    )

    assert title.heading_level == 1
