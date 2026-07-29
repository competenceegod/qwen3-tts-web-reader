from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from booksite.quality.rules import NativeTextStatus


class TocEntry(BaseModel):
    level: int = Field(ge=1)
    title: str = Field(min_length=1)
    start_page: int = Field(ge=1)
    end_page: int | None = Field(default=None, ge=1)
    source: Literal["pdf_bookmark", "printed_toc", "inferred"]
    slug: str
    children: list[TocEntry] = Field(default_factory=list)


class PageAudit(BaseModel):
    page_index: int = Field(ge=0)
    printed_page_label: str | None = None
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    rotation: int
    native_text: str
    native_text_char_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    text_block_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    link_count: int = Field(ge=0)
    image_coverage_ratio: float = Field(ge=0, le=1)
    replacement_character_count: int = Field(ge=0)
    font_names: list[str]
    native_text_status: NativeTextStatus


class AuditReport(BaseModel):
    source_pdf: Path
    source_sha256: str
    book_id: str
    title: str | None
    author: str | None
    language: str | None
    total_page_count: int = Field(ge=1)
    page_count: int = Field(ge=1)
    pdf_metadata: dict[str, Any]
    original_toc: list[TocEntry]
    pages: list[PageAudit]
