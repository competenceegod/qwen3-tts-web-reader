from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

import pymupdf

from booksite.assemble.slugger import stable_slug
from booksite.models.reports import AuditReport, PageAudit, TocEntry
from booksite.quality.rules import classify_native_text


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def book_id_for_source(path: Path, source_sha256: str) -> str:
    decomposed = unicodedata.normalize("NFKD", path.stem)
    ascii_stem = decomposed.encode("ascii", "ignore").decode("ascii")
    readable_stem = re.sub(r"[^a-z0-9]+", "-", ascii_stem.casefold()).strip("-")
    return f"{(readable_stem or 'book')[:80]}-{source_sha256[:8]}"


def _image_coverage(page: pymupdf.Page) -> float:
    page_area = max(page.rect.get_area(), 1)
    covered_area = 0.0
    for image in page.get_image_info(hashes=False, xrefs=False):
        bbox = pymupdf.Rect(image["bbox"]) & page.rect
        covered_area += max(bbox.get_area(), 0)
    return min(covered_area / page_area, 1.0)


def _font_names(text_dict: dict[str, Any]) -> list[str]:
    fonts: set[str] = set()
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if font := span.get("font"):
                    fonts.add(str(font))
    return sorted(fonts)


def _toc_entries(document: pymupdf.Document, page_limit: int) -> list[TocEntry]:
    raw_entries = document.get_toc(simple=True)
    in_range = [entry for entry in raw_entries if 1 <= int(entry[2]) <= page_limit]
    entries: list[TocEntry] = []
    for index, (level, title, start_page, *_) in enumerate(in_range):
        end_page = page_limit
        for next_level, _, next_page, *_ in in_range[index + 1 :]:
            if int(next_level) <= int(level):
                end_page = min(int(next_page) - 1, page_limit)
                break
        entries.append(
            TocEntry(
                level=int(level),
                title=str(title).strip(),
                start_page=int(start_page),
                end_page=max(int(start_page), end_page),
                source="pdf_bookmark",
                slug=stable_slug(str(title), int(start_page)),
            )
        )
    return entries


def audit_pdf(pdf_path: str | Path, max_pages: int | None = None) -> AuditReport:
    """Audit a PDF without invoking OCR or layout models."""
    source_path = Path(pdf_path).expanduser().resolve()
    source_sha256 = _file_sha256(source_path)
    with pymupdf.open(source_path) as document:
        total_page_count = document.page_count
        page_count = min(total_page_count, max_pages or total_page_count)
        metadata = dict(document.metadata or {})
        pages: list[PageAudit] = []
        for page_index in range(page_count):
            page = document[page_index]
            native_text = page.get_text("text", sort=True)
            text_dict = page.get_text("dict", sort=True)
            image_coverage_ratio = _image_coverage(page)
            pages.append(
                PageAudit(
                    page_index=page_index,
                    printed_page_label=page.get_label() or None,
                    width=page.rect.width,
                    height=page.rect.height,
                    rotation=page.rotation,
                    native_text=native_text,
                    native_text_char_count=len(native_text.strip()),
                    word_count=len(page.get_text("words", sort=True)),
                    text_block_count=len(page.get_text("blocks", sort=True)),
                    image_count=len(page.get_images(full=True)),
                    link_count=len(page.get_links()),
                    image_coverage_ratio=image_coverage_ratio,
                    replacement_character_count=native_text.count("\ufffd"),
                    font_names=_font_names(text_dict),
                    native_text_status=classify_native_text(
                        native_text,
                        image_coverage_ratio=image_coverage_ratio,
                    ),
                )
            )

        title = metadata.get("title") or None
        author = metadata.get("author") or None
        return AuditReport(
            source_pdf=source_path,
            source_sha256=source_sha256,
            book_id=book_id_for_source(source_path, source_sha256),
            title=title,
            author=author,
            language=metadata.get("language") or None,
            total_page_count=total_page_count,
            page_count=page_count,
            pdf_metadata=metadata,
            original_toc=_toc_entries(document, page_count),
            pages=pages,
        )
