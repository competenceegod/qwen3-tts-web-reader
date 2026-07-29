from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import pymupdf

from booksite.models.book_ir import BlockIR, BookIR, PageIR, SectionIR, WarningIR
from booksite.models.reports import AuditReport, TocEntry
from booksite.normalize.headers_footers import (
    MarginalLine,
    find_repeated_marginal_text,
    normalize_marginal_text,
)
from booksite.normalize.text import dehyphenate_line_breaks, normalize_unicode
from booksite.quality.rules import NativeTextStatus

_LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_MONO_HINTS = ("mono", "courier", "code", "consol")


def _line_text(line: dict[str, Any]) -> str:
    return "".join(str(span.get("text", "")) for span in line.get("spans", [])).strip()


def _all_marginal_lines(document: pymupdf.Document, page_count: int) -> list[MarginalLine]:
    lines: list[MarginalLine] = []
    for page_index in range(page_count):
        page = document[page_index]
        height = max(page.rect.height, 1)
        for block in page.get_text("dict", sort=True).get("blocks", []):
            for line in block.get("lines", []):
                text = _line_text(line)
                if text:
                    lines.append(MarginalLine(page_index, text, float(line["bbox"][1]) / height))
    return lines


def _toc_by_page(entries: list[TocEntry]) -> dict[int, list[TocEntry]]:
    grouped: dict[int, list[TocEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.start_page].append(entry)
    return grouped


def _escape_mdx(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("{", "&#123;")
        .replace("}", "&#125;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _block_from_pdf(
    raw_block: dict[str, Any],
    page_index: int,
    order: int,
    repeated_marginals: set[str],
    toc_titles: dict[str, int],
    typical_font_size: float,
    page_height: float,
) -> BlockIR | None:
    raw_lines = raw_block.get("lines", [])
    kept_lines: list[dict[str, Any]] = []
    for line in raw_lines:
        text = _line_text(line)
        vertical_ratio = float(line["bbox"][1]) / max(page_height, 1)
        marginal = vertical_ratio <= 0.1 or vertical_ratio >= 0.9
        if marginal and normalize_marginal_text(text) in repeated_marginals:
            continue
        kept_lines.append(line)
    if not kept_lines:
        return None

    texts = [_line_text(line) for line in kept_lines if _line_text(line)]
    if not texts:
        return None
    text = normalize_unicode("\n".join(texts)).strip()
    normalized = " ".join(text.casefold().split())
    spans = [span for line in kept_lines for span in line.get("spans", [])]
    char_total = sum(len(str(span.get("text", ""))) for span in spans) or 1
    mono_chars = sum(
        len(str(span.get("text", "")))
        for span in spans
        if any(hint in str(span.get("font", "")).casefold() for hint in _MONO_HINTS)
    )
    max_size = max((float(span.get("size", 0)) for span in spans), default=0)

    block_type = "paragraph"
    heading_level = None
    markdown: str
    if normalized in toc_titles:
        block_type = "title"
        heading_level = toc_titles[normalized]
        markdown = f"{'#' * heading_level} {_escape_mdx(text)}"
    elif mono_chars / char_total >= 0.45 and len(text) >= 8:
        block_type = "code"
        markdown = f"```text\n{text}\n```"
    elif max_size >= max(15, typical_font_size * 1.35):
        block_type = "title"
        heading_level = 2
        markdown = f"## {_escape_mdx(text)}"
    elif all(_LIST_MARKER.match(line) for line in texts):
        block_type = "list"
        markdown = "\n".join(_escape_mdx(line) for line in texts)
    else:
        joined = dehyphenate_line_breaks(text)
        markdown = _escape_mdx(" ".join(joined.splitlines()))

    bbox = tuple(float(value) for value in raw_block["bbox"])
    return BlockIR(
        block_id=f"p{page_index + 1:04d}-b{order + 1:03d}",
        page_index=page_index,
        order=order,
        type=block_type,
        bbox=bbox,
        text=text,
        markdown=markdown,
        heading_level=heading_level,
        source_engine="native",
        confidence=1.0,
    )


def _page_ir(
    page: pymupdf.Page,
    audit_page: Any,
    repeated_marginals: set[str],
    entries: list[TocEntry],
) -> PageIR:
    text_dict = page.get_text("dict", sort=True)
    sizes = [
        float(span.get("size", 0))
        for block in text_dict.get("blocks", [])
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]
    typical_size = median(sizes) if sizes else 11
    toc_titles = {" ".join(entry.title.casefold().split()): entry.level for entry in entries}
    blocks = []
    for order, raw_block in enumerate(text_dict.get("blocks", [])):
        if raw_block.get("type", 0) != 0:
            continue
        block = _block_from_pdf(
            raw_block,
            page.number,
            order,
            repeated_marginals,
            toc_titles,
            typical_size,
            page.rect.height,
        )
        if block is not None:
            blocks.append(block)

    score_by_status = {
        NativeTextStatus.TEXT_GOOD: 1.0,
        NativeTextStatus.TEXT_SUSPECT: 0.65,
        NativeTextStatus.MIXED: 0.45,
        NativeTextStatus.IMAGE_ONLY: 0.25,
    }
    fallback_reasons = []
    if audit_page.native_text_status is not NativeTextStatus.TEXT_GOOD:
        fallback_reasons.append(f"native_text_{audit_page.native_text_status.value.casefold()}")
    return PageIR(
        page_index=page.number,
        printed_page_label=audit_page.printed_page_label,
        width=page.rect.width,
        height=page.rect.height,
        native_text=audit_page.native_text,
        native_text_char_count=audit_page.native_text_char_count,
        blocks=blocks,
        primary_engine="native",
        selected_engine="native",
        quality_score=score_by_status[audit_page.native_text_status],
        fallback_reasons=fallback_reasons,
    )


def _top_sections(entries: list[TocEntry], page_count: int, title: str) -> list[TocEntry]:
    top_level = [entry for entry in entries if entry.level == 1]
    if top_level:
        if top_level[0].start_page > 1:
            from booksite.assemble.slugger import stable_slug

            front_matter_title = "Front Matter"
            return [
                TocEntry(
                    level=1,
                    title=front_matter_title,
                    start_page=1,
                    end_page=top_level[0].start_page - 1,
                    source="inferred",
                    slug=stable_slug(front_matter_title, 1),
                ),
                *top_level,
            ]
        return top_level
    from booksite.assemble.slugger import stable_slug

    return [
        TocEntry(
            level=1,
            title=title,
            start_page=1,
            end_page=page_count,
            source="inferred",
            slug=stable_slug(title, 1),
        )
    ]


def _infer_title(audit: AuditReport) -> str:
    if audit.title:
        return audit.title
    for page in audit.pages:
        lines = [line.strip() for line in page.native_text.splitlines() if line.strip()]
        if lines and len(lines[0]) >= 4:
            return lines[0]
    return Path(audit.source_pdf).stem.replace("_", " ")


def _merge_fenced_code(previous: str, current: str) -> str | None:
    previous_lines = previous.splitlines()
    current_lines = current.splitlines()
    if (
        len(previous_lines) < 3
        or len(current_lines) < 3
        or not previous_lines[0].startswith("```")
        or not current_lines[0].startswith("```")
        or previous_lines[-1] != "```"
        or current_lines[-1] != "```"
    ):
        return None
    return "\n".join(
        [
            previous_lines[0],
            *previous_lines[1:-1],
            *current_lines[1:-1],
            "```",
        ]
    )


def _section_markdown(
    section: TocEntry,
    pages: list[PageIR],
    nested_entries: dict[int, list[TocEntry]],
) -> str:
    parts = [f"# {_escape_mdx(section.title)}"]
    previous_block_type: str | None = None
    source_pages = range(section.start_page, (section.end_page or section.start_page) + 1)
    for page_number in source_pages:
        for entry in nested_entries.get(page_number, []):
            if entry.level > section.level:
                parts.append(f"{'#' * min(entry.level, 6)} {_escape_mdx(entry.title)}")
                previous_block_type = "title"
        page = pages[page_number - 1]
        page_entries = nested_entries.get(page_number, [])
        entry_titles = {" ".join(entry.title.casefold().split()) for entry in page_entries}
        section_title = " ".join(section.title.casefold().split())
        for block in page.blocks:
            normalized = " ".join((block.text or "").casefold().split())
            partial_section_title = (
                block.type == "title" and len(normalized) >= 8 and normalized in section_title
            )
            if normalized == section_title or normalized in entry_titles or partial_section_title:
                continue
            if block.markdown:
                if block.type == "code" and previous_block_type == "code":
                    merged_code = _merge_fenced_code(parts[-1], block.markdown)
                    if merged_code is not None:
                        parts[-1] = merged_code
                        continue
                if block.type == "paragraph" and previous_block_type == "paragraph":
                    combined = f"{parts[-1]}\n\n{block.markdown}"
                    dehyphenated = dehyphenate_line_breaks(combined)
                    if dehyphenated != combined:
                        parts[-1] = dehyphenated
                        continue
                parts.append(block.markdown)
                previous_block_type = block.type
    end_page = section.end_page or section.start_page
    page_label = (
        f"PDF page {section.start_page}"
        if end_page == section.start_page
        else f"PDF pages {section.start_page}–{end_page}"
    )
    parts.append(f"*{page_label}*")
    return "\n\n".join(parts).strip() + "\n"


def assemble_native_book(pdf_path: str | Path, audit: AuditReport) -> BookIR:
    """Build a validated BookIR using only local native PDF data."""
    title = _infer_title(audit)
    repeated_marginals: set[str]
    with pymupdf.open(pdf_path) as document:
        repeated_marginals = find_repeated_marginal_text(
            _all_marginal_lines(document, audit.page_count),
            page_count=audit.page_count,
        )
        grouped_toc = _toc_by_page(audit.original_toc)
        pages = [
            _page_ir(
                document[index],
                audit.pages[index],
                repeated_marginals,
                grouped_toc.get(index + 1, []),
            )
            for index in range(audit.page_count)
        ]

    top_sections = _top_sections(audit.original_toc, audit.page_count, title)
    sections = [
        SectionIR(
            section_id=entry.slug,
            title=entry.title,
            level=entry.level,
            slug=entry.slug,
            order=order,
            source_pages=list(range(entry.start_page, (entry.end_page or entry.start_page) + 1)),
            markdown=_section_markdown(entry, pages, _toc_by_page(audit.original_toc)),
        )
        for order, entry in enumerate(top_sections, start=1)
    ]
    warnings = [
        WarningIR(
            code="native_text_review",
            message=f"Native text status: {page.native_text_status.value}",
            page_index=page.page_index,
        )
        for page in audit.pages
        if page.native_text_status is not NativeTextStatus.TEXT_GOOD
    ]
    return BookIR(
        book_id=audit.book_id,
        source_pdf=audit.source_pdf,
        source_sha256=audit.source_sha256,
        title=title,
        author=audit.author,
        language=audit.language,
        page_count=audit.page_count,
        pdf_metadata=audit.pdf_metadata,
        original_toc=audit.original_toc,
        resolved_toc=audit.original_toc,
        pages=pages,
        sections=sections,
        warnings=warnings,
        engine_versions={"pymupdf": pymupdf.__version__},
    )
