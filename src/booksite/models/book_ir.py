from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from booksite.models.reports import TocEntry

BlockType = Literal[
    "title",
    "paragraph",
    "list",
    "code",
    "formula",
    "table",
    "image",
    "chart",
    "caption",
    "footnote",
    "reference",
    "header",
    "footer",
    "page_number",
    "unknown",
]


class BlockIR(BaseModel):
    block_id: str
    page_index: int = Field(ge=0)
    order: int = Field(ge=0)
    type: BlockType
    bbox: tuple[float, float, float, float] | None = None
    text: str | None = None
    markdown: str | None = None
    latex: str | None = None
    html: str | None = None
    heading_level: int | None = Field(default=None, ge=1, le=6)
    asset_path: str | None = None
    caption: str | None = None
    source_engine: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def title_has_heading_level(self) -> BlockIR:
        if self.type == "title" and self.heading_level is None:
            raise ValueError("title blocks require heading_level")
        return self


class PageIR(BaseModel):
    page_index: int = Field(ge=0)
    printed_page_label: str | None = None
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    native_text: str
    native_text_char_count: int = Field(ge=0)
    blocks: list[BlockIR]
    primary_engine: str
    selected_engine: str
    quality_score: float = Field(ge=0, le=1)
    fallback_reasons: list[str] = Field(default_factory=list)
    rendered_page_path: str | None = None


class SectionIR(BaseModel):
    section_id: str
    title: str
    level: int = Field(ge=1, le=6)
    slug: str
    order: int = Field(ge=1)
    source_pages: list[int]
    markdown: str
    children: list[str] = Field(default_factory=list)


class AssetIR(BaseModel):
    asset_id: str
    source_page: int = Field(ge=1)
    path: str
    sha256: str
    media_type: str
    caption: str | None = None


class WarningIR(BaseModel):
    code: str
    message: str
    page_index: int | None = Field(default=None, ge=0)
    severity: Literal["info", "warning", "error"] = "warning"


class BookIR(BaseModel):
    schema_version: str = "1.0"
    book_id: str
    source_pdf: Path
    source_sha256: str
    title: str | None = None
    author: str | None = None
    language: str | None = None
    page_count: int = Field(ge=1)
    pdf_metadata: dict[str, Any] = Field(default_factory=dict)
    original_toc: list[TocEntry] = Field(default_factory=list)
    resolved_toc: list[TocEntry] = Field(default_factory=list)
    pages: list[PageIR]
    sections: list[SectionIR]
    assets: list[AssetIR] = Field(default_factory=list)
    warnings: list[WarningIR] = Field(default_factory=list)
    engine_versions: dict[str, str] = Field(default_factory=dict)
