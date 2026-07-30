from __future__ import annotations

import base64
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import pymupdf

from booksite.models.book_ir import (
    BlockIR,
    BookIR,
    CodeLineIR,
    CodeSpanIR,
    CodeStyleIR,
    PageIR,
    SectionIR,
    WarningIR,
)
from booksite.models.reports import AuditReport, TocEntry
from booksite.normalize.headers_footers import (
    MarginalLine,
    find_repeated_marginal_text,
    normalize_marginal_text,
)
from booksite.normalize.text import dehyphenate_line_breaks, normalize_unicode
from booksite.quality.rules import NativeTextStatus

_LIST_MARKER = re.compile(r"^\s*(?P<marker>[-*•]|\d+[.)])\s+(?P<content>.+)$")
_LIST_MARKER_ONLY = re.compile(r"^\s*(?P<marker>[-*•]|\d+[.)])\s*$")
_SHORT_CODE_SYNTAX = re.compile(r"^[\s()[\]{},.:;|&+*/%=<>!~^-]+$")
_MARKDOWN_PUNCTUATION = re.compile(r"([\\`*_[\]()#!|])")
_MDX_ESM_PREFIX = re.compile(r"^(import|export)[ \t]+")
_MONO_HINTS = ("mono", "courier", "code", "consol")
_LIST_INDENT_POINTS = 24.0
_URL_PREFIX_AND_BASE = re.compile(r"^(?P<prefix>[A-Za-z][^\n]*?:\s+)(?P<url>https?://[^\s]+/)$")
_URL_PATH_CONTINUATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")
_CODE_STATEMENT = re.compile(
    r"""^\s*(?:
        (?:from\s+\S+\s+import|import\s+\S+|def\s+\w+|class\s+\w+|async\s+def\s+\w+)\b
        |(?:if|elif|else|for|while|with|try|except|finally|return|raise|yield|assert)\b
        |(?:pip|conda|python|python3|uv|npm|pnpm|ollama|docker|git|curl|wget|bash|zsh|export)\s+
        |[@#$!%]
        |(?:[A-Za-z_]\w*(?:[.\[][^=]*)?)\s*=\s*\S
        |[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*\(
        |(?:\.\.\.|[)\]}]+[|,;]?)
    )""",
    re.VERBOSE,
)


def _raw_line_text(line: dict[str, Any]) -> str:
    return "".join(str(span.get("text", "")) for span in line.get("spans", []))


def _line_text(line: dict[str, Any]) -> str:
    return _raw_line_text(line).strip()


def _markdown_list_item(marker: str, content: str) -> str:
    markdown_marker = "-" if marker in {"-", "*", "•"} else marker
    return f"{markdown_marker} {_escape_mdx(content)}"


def _list_markdown(lines: list[str]) -> str | None:
    items: list[str] = []
    pending_marker: str | None = None
    for line in lines:
        if match := _LIST_MARKER.match(line):
            if pending_marker is not None:
                return None
            items.append(_markdown_list_item(match.group("marker"), match.group("content")))
            continue
        if marker_match := _LIST_MARKER_ONLY.match(line):
            if pending_marker is not None:
                return None
            pending_marker = marker_match.group("marker")
            continue
        if pending_marker is not None:
            items.append(_markdown_list_item(pending_marker, line))
            pending_marker = None
            continue
        if not items:
            return None
        items[-1] = dehyphenate_line_breaks(f"{items[-1]}\n{_escape_mdx(line)}").replace("\n", " ")
    if pending_marker is not None or not items:
        return None
    return "\n".join(items)


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
    html_safe = (
        text.replace("&", "&amp;")
        .replace("{", "&#123;")
        .replace("}", "&#125;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    markdown_safe = _MARKDOWN_PUNCTUATION.sub(r"\\\1", html_safe)
    markdown_safe = markdown_safe.replace(r"&\#123;", "&#123;").replace(r"&\#125;", "&#125;")
    return _MDX_ESM_PREFIX.sub(r"\1&#32;", markdown_safe)


def _integer_color(value: object) -> str:
    try:
        color = int(value)
    except (OverflowError, TypeError, ValueError):
        color = 0
    return f"#{max(0, min(color, 0xFFFFFF)):06x}"


def _bounded_float(
    value: object,
    fallback: float,
    *,
    minimum: float = 0.1,
    maximum: float = 256.0,
) -> float:
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return fallback
    if not math.isfinite(number):
        return fallback
    return max(minimum, min(number, maximum))


def _bounded_int(value: object, fallback: int = 0) -> int:
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError):
        return fallback


def _font_family(value: object) -> str:
    font_family = "".join(
        character
        for character in str(value or "monospace")
        if character.isprintable() and character not in "\r\n"
    ).strip()
    return (font_family or "monospace")[:256]


def _drawing_color(value: object, fallback: str) -> str:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return fallback
    try:
        channels = [max(0, min(round(float(channel) * 255), 255)) for channel in value[:3]]
    except (OverflowError, TypeError, ValueError):
        return fallback
    return f"#{channels[0]:02x}{channels[1]:02x}{channels[2]:02x}"


def _code_lines(lines: list[dict[str, Any]]) -> list[CodeLineIR]:
    styled_lines: list[CodeLineIR] = []
    for line in lines:
        spans = []
        for span in line.get("spans", []):
            text = str(span.get("text", ""))
            if not text:
                continue
            flags = _bounded_int(span.get("flags", 0))
            font_family = _font_family(span.get("font"))
            spans.append(
                CodeSpanIR(
                    text=text,
                    color=_integer_color(span.get("color", 0)),
                    font_family=font_family,
                    font_size_pt=_bounded_float(span.get("size", 9.0), 9.0),
                    bold=bool(flags & 16) or "bold" in font_family.casefold(),
                    italic=bool(flags & 2) or "italic" in font_family.casefold(),
                )
            )
        styled_lines.append(CodeLineIR(spans=spans))
    return styled_lines


def _code_style_for_bbox(
    drawings: list[dict[str, Any]],
    bbox: tuple[float, float, float, float],
    font_size_pt: float,
) -> CodeStyleIR | None:
    style, _ = _code_surface_for_bbox(drawings, bbox, font_size_pt)
    return style


def _code_surface_for_bbox(
    drawings: list[dict[str, Any]],
    bbox: tuple[float, float, float, float],
    font_size_pt: float,
) -> tuple[CodeStyleIR | None, tuple[float, float, float, float] | None]:
    block_rect = pymupdf.Rect(bbox)
    center = (block_rect.x0 + block_rect.x1) / 2, (block_rect.y0 + block_rect.y1) / 2
    surfaces: list[tuple[float, pymupdf.Rect, dict[str, Any]]] = []
    for drawing in drawings:
        if drawing.get("fill") is None or drawing.get("rect") is None:
            continue
        rect = pymupdf.Rect(drawing["rect"])
        if rect.contains(center):
            surfaces.append((rect.get_area(), rect, drawing))
    if not surfaces:
        return None, None

    _, surface_rect, surface = min(surfaces, key=lambda item: item[0])
    border_color = "#d8dee9"
    for drawing in drawings:
        if drawing.get("color") is None or drawing.get("rect") is None:
            continue
        line_rect = pymupdf.Rect(drawing["rect"])
        same_vertical_extent = (
            abs(line_rect.y0 - surface_rect.y0) <= 2 and abs(line_rect.y1 - surface_rect.y1) <= 2
        )
        if same_vertical_extent and abs(line_rect.x0 - surface_rect.x0) <= 4:
            border_color = _drawing_color(drawing["color"], border_color)
            break
    return (
        CodeStyleIR(
            background_color=_drawing_color(surface.get("fill"), "#f8f8f8"),
            border_color=border_color,
            font_size_pt=font_size_pt,
        ),
        tuple(float(value) for value in surface_rect),
    )


def _looks_like_code(text: str) -> bool:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    code_like = sum(
        bool(_CODE_STATEMENT.match(line) or _SHORT_CODE_SYNTAX.fullmatch(line)) for line in lines
    )
    return code_like >= max(1, math.ceil(len(lines) / 2))


def _block_from_pdf(
    raw_block: dict[str, Any],
    page_index: int,
    order: int,
    repeated_marginals: set[str],
    toc_titles: dict[str, int],
    typical_font_size: float,
    page_height: float,
    code_style: CodeStyleIR | None = None,
) -> BlockIR | None:
    raw_lines = raw_block.get("lines", [])
    kept_lines: list[dict[str, Any]] = []
    for line in raw_lines:
        text = _line_text(line)
        vertical_ratio = float(line["bbox"][1]) / max(page_height, 1)
        marginal = vertical_ratio <= 0.1 or vertical_ratio >= 0.9
        normalized_marginal = normalize_marginal_text(text)
        if marginal and (
            normalized_marginal == "<page-number>" or normalized_marginal in repeated_marginals
        ):
            continue
        kept_lines.append(line)
    if not kept_lines:
        return None

    texts = [_line_text(line) for line in kept_lines if _line_text(line)]
    if not texts:
        return None
    text = normalize_unicode("\n".join(texts)).strip()
    code_text = normalize_unicode(
        "\n".join(_raw_line_text(line).rstrip() for line in kept_lines)
    ).strip("\n")
    list_markdown = _list_markdown(texts)
    normalized = " ".join(text.casefold().split())
    spans = [span for line in kept_lines for span in line.get("spans", [])]
    char_total = sum(len(str(span.get("text", ""))) for span in spans) or 1
    mono_chars = sum(
        len(str(span.get("text", "")))
        for span in spans
        if any(hint in str(span.get("font", "")).casefold() for hint in _MONO_HINTS)
    )
    max_size = max(
        (
            _bounded_float(
                span.get("size", 0),
                0,
                minimum=0,
            )
            for span in spans
        ),
        default=0,
    )

    block_type = "paragraph"
    block_text = text
    heading_level = None
    markdown: str
    if normalized in toc_titles:
        block_type = "title"
        heading_level = toc_titles[normalized]
        markdown = f"{'#' * heading_level} {_escape_mdx(text)}"
    elif (
        mono_chars / char_total >= 0.45 and (len(text) >= 8 or _SHORT_CODE_SYNTAX.fullmatch(text))
    ) or (code_style is not None and _looks_like_code(code_text)):
        block_type = "code"
        block_text = code_text
        markdown = f"```text\n{code_text}\n```"
    elif max_size >= max(15, typical_font_size * 1.35):
        block_type = "title"
        heading_level = 2
        markdown = f"## {_escape_mdx(text)}"
    elif list_markdown is not None:
        block_type = "list"
        markdown = list_markdown
    else:
        joined = dehyphenate_line_breaks(text)
        markdown = _escape_mdx(" ".join(joined.splitlines()))

    bbox = tuple(float(value) for value in raw_block["bbox"])
    styled_code_lines: list[CodeLineIR] = []
    if block_type == "code" or code_style is not None:
        styled_code_lines = _code_lines(kept_lines)
        code_sizes = [span.font_size_pt for line in styled_code_lines for span in line.spans]
        effective_size = median(code_sizes) if code_sizes else max(typical_font_size, 0.1)
        code_style = (
            code_style
            or CodeStyleIR(
                background_color="#f8f8f8",
                border_color="#d8dee9",
                font_size_pt=effective_size,
            )
        ).model_copy(update={"font_size_pt": effective_size})
    return BlockIR(
        block_id=f"p{page_index + 1:04d}-b{order + 1:03d}",
        page_index=page_index,
        order=order,
        type=block_type,
        bbox=bbox,
        text=block_text,
        markdown=markdown,
        code_lines=styled_code_lines,
        code_style=code_style,
        heading_level=heading_level,
        source_engine="native",
        confidence=1.0,
    )


def _nearby_left_aligned(previous: BlockIR, current: BlockIR) -> bool:
    if previous.page_index != current.page_index or previous.bbox is None or current.bbox is None:
        return False
    vertical_gap = current.bbox[1] - previous.bbox[3]
    return -1.0 <= vertical_gap <= 6.0 and abs(current.bbox[0] - previous.bbox[0]) <= 3.0


def _url_callout_markdown(
    prefix: str,
    url: str,
    suffix: str,
    style: CodeStyleIR,
) -> str:
    payload = {
        "prefix": prefix,
        "url": url,
        "suffix": suffix,
        "backgroundColor": style.background_color,
        "borderColor": style.border_color,
    }
    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    ).decode()
    return f'<PdfUrlCallout data="{encoded}" />'


def _same_code_surface(first: CodeStyleIR, second: CodeStyleIR) -> bool:
    return (
        first.background_color == second.background_color
        and first.border_color == second.border_color
    )


def _color_channels(color: str) -> tuple[int, int, int] | None:
    value = color.removeprefix("#")
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None


def _is_known_dark_code_surface(style: CodeStyleIR) -> bool:
    """Recognize the PDF's Dracula-like output palette without swallowing dark callouts."""
    background = _color_channels(style.background_color)
    border = _color_channels(style.border_color)
    if background is None or border is None:
        return False
    expected_background = (40, 42, 54)
    expected_border = (68, 71, 90)
    return all(
        abs(actual - expected) <= 4
        for actual, expected in zip(
            background + border,
            expected_background + expected_border,
            strict=True,
        )
    )


def _promote_shaded_code_surfaces(
    blocks: list[BlockIR],
    surface_by_block: dict[str, tuple[float, float, float, float]],
    page_area: float,
) -> list[BlockIR]:
    grouped: dict[tuple[float, float, float, float], list[int]] = defaultdict(list)
    for index, block in enumerate(blocks):
        if surface := surface_by_block.get(block.block_id):
            grouped[surface].append(index)

    promoted = list(blocks)
    for surface, indices in grouped.items():
        surface_area = max(0.0, surface[2] - surface[0]) * max(0.0, surface[3] - surface[1])
        if page_area > 0 and surface_area / page_area > 0.5:
            continue
        anchors = [blocks[index] for index in indices if blocks[index].type == "code"]
        surface_blocks = [
            blocks[index] for index in indices if blocks[index].code_style is not None
        ]
        dark_surface_blocks = [
            block
            for block in surface_blocks
            if block.code_style is not None and _is_known_dark_code_surface(block.code_style)
        ]
        if not anchors and not dark_surface_blocks:
            continue
        all_sizes = [
            span.font_size_pt
            for index in indices
            for line in blocks[index].code_lines
            for span in line.spans
        ]
        common_style = (anchors or dark_surface_blocks)[0].code_style
        if common_style is None:
            continue
        if all_sizes:
            common_style = common_style.model_copy(update={"font_size_pt": median(all_sizes)})
        for index in indices:
            block = blocks[index]
            if block.type not in {"code", "list", "paragraph"} or not block.code_lines:
                continue
            code_text = "\n".join(
                "".join(span.text for span in line.spans) for line in block.code_lines
            ).strip("\n")
            promoted[index] = block.model_copy(
                update={
                    "type": "code",
                    "text": code_text,
                    "markdown": f"```text\n{code_text}\n```",
                    "code_style": common_style,
                    "heading_level": None,
                }
            )
    return promoted


def _merge_pdf_url_callouts(blocks: list[BlockIR]) -> list[BlockIR]:
    """Join a PDF prose line and monospaced URL continuations into one callout."""
    merged: list[BlockIR] = []
    index = 0
    while index < len(blocks):
        if index + 2 >= len(blocks):
            merged.extend(blocks[index:])
            break
        prose, mixed_url, url_tail = blocks[index : index + 3]
        match = (
            _URL_PREFIX_AND_BASE.fullmatch((mixed_url.text or "").strip())
            if prose.type == "paragraph"
            and (prose.text or "").rstrip().endswith("-")
            and mixed_url.type in {"paragraph", "code"}
            and url_tail.type in {"paragraph", "code"}
            and mixed_url.code_style is not None
            and url_tail.code_style is not None
            and _same_code_surface(mixed_url.code_style, url_tail.code_style)
            and _nearby_left_aligned(prose, mixed_url)
            and _nearby_left_aligned(mixed_url, url_tail)
            else None
        )
        tail = (url_tail.text or "").strip()
        suffix = tail[-1:] if tail.endswith((".", ",", ";", ":")) else ""
        path = tail[: -len(suffix)] if suffix else tail
        if match is None or _URL_PATH_CONTINUATION.fullmatch(path) is None:
            merged.append(prose)
            index += 1
            continue

        prefix = dehyphenate_line_breaks(f"{(prose.text or '').rstrip()}\n{match.group('prefix')}")
        url = f"{match.group('url')}{path}"
        text = f"{prefix}{url}{suffix}"
        bboxes = [block.bbox for block in (prose, mixed_url, url_tail) if block.bbox is not None]
        bbox = (
            (
                min(item[0] for item in bboxes),
                min(item[1] for item in bboxes),
                max(item[2] for item in bboxes),
                max(item[3] for item in bboxes),
            )
            if bboxes
            else prose.bbox
        )
        merged.append(
            prose.model_copy(
                update={
                    "bbox": bbox,
                    "text": text,
                    "markdown": _url_callout_markdown(
                        prefix,
                        url,
                        suffix,
                        mixed_url.code_style,
                    ),
                }
            )
        )
        index += 3
    return merged


def _page_ir(
    page: pymupdf.Page,
    audit_page: Any,
    repeated_marginals: set[str],
    entries: list[TocEntry],
) -> PageIR:
    text_dict = page.get_text("dict", sort=True)
    drawings = page.get_drawings()
    sizes = [
        _bounded_float(span.get("size", 0), 0, minimum=0)
        for block in text_dict.get("blocks", [])
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]
    typical_size = median(sizes) if sizes else 11
    toc_titles = {" ".join(entry.title.casefold().split()): entry.level for entry in entries}
    blocks = []
    surface_by_block: dict[str, tuple[float, float, float, float]] = {}
    for order, raw_block in enumerate(text_dict.get("blocks", [])):
        if raw_block.get("type", 0) != 0:
            continue
        bbox = tuple(float(value) for value in raw_block["bbox"])
        code_style, surface = _code_surface_for_bbox(
            drawings,
            bbox,
            typical_size,
        )
        if surface is not None:
            surface_area = max(0.0, surface[2] - surface[0]) * max(0.0, surface[3] - surface[1])
            if page.rect.get_area() > 0 and surface_area / page.rect.get_area() > 0.5:
                code_style = None
                surface = None
        block = _block_from_pdf(
            raw_block,
            page.number,
            order,
            repeated_marginals,
            toc_titles,
            typical_size,
            page.rect.height,
            code_style,
        )
        if block is not None:
            blocks.append(block)
            if surface is not None:
                surface_by_block[block.block_id] = surface
    blocks = _promote_shaded_code_surfaces(
        blocks,
        surface_by_block,
        page.rect.get_area(),
    )
    blocks = _merge_pdf_url_callouts(blocks)

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


def _merge_fenced_code(
    previous: str,
    current: str,
    preserve_blank_line: bool = False,
) -> str | None:
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
            *([""] if preserve_blank_line else []),
            *current_lines[1:-1],
            "```",
        ]
    )


def _code_blocks_have_blank_line(previous: BlockIR | None, current: BlockIR) -> bool:
    if (
        previous is None
        or previous.page_index != current.page_index
        or previous.bbox is None
        or current.bbox is None
    ):
        return False
    previous_lines = max(1, len((previous.text or "").splitlines()))
    line_pitch = (previous.bbox[3] - previous.bbox[1]) / previous_lines
    vertical_gap = current.bbox[1] - previous.bbox[3]
    return vertical_gap > max(8.0, line_pitch * 0.75)


def _indent_list(markdown: str, base_x: float | None, block: BlockIR) -> str:
    if base_x is None or block.bbox is None:
        return markdown
    level = max(0, round((block.bbox[0] - base_x) / _LIST_INDENT_POINTS))
    prefix = "    " * level
    return "\n".join(f"{prefix}{line}" if line else line for line in markdown.splitlines())


def _styled_code_markdown(blocks: list[BlockIR]) -> str:
    first_style = blocks[0].code_style
    if first_style is None:
        raise ValueError("styled code blocks require code_style")
    lines: list[list[dict[str, object]]] = []
    previous: BlockIR | None = None
    for block in blocks:
        if previous is not None and _code_blocks_have_blank_line(previous, block):
            lines.append([])
        lines.extend(
            [
                [
                    {
                        "text": span.text,
                        "color": span.color,
                        "fontFamily": span.font_family,
                        "fontSizePt": span.font_size_pt,
                        "bold": span.bold,
                        "italic": span.italic,
                    }
                    for span in line.spans
                ]
                for line in block.code_lines
            ]
        )
        previous = block
    payload = {
        "backgroundColor": first_style.background_color,
        "borderColor": first_style.border_color,
        "fontSizePt": first_style.font_size_pt,
        "lines": lines,
    }
    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    ).decode()
    return f'<PdfCodeBlock data="{encoded}" />'


def _section_markdown(
    section: TocEntry,
    pages: list[PageIR],
    nested_entries: dict[int, list[TocEntry]],
) -> str:
    parts = [f"# {_escape_mdx(section.title)}"]
    previous_block_type: str | None = None
    previous_block: BlockIR | None = None
    list_base_x: float | None = None
    list_level = 0
    pending_styled_code: list[BlockIR] = []
    pending_styled_code_indent = 0

    def flush_styled_code() -> None:
        if pending_styled_code:
            markdown = _styled_code_markdown(pending_styled_code)
            if pending_styled_code_indent:
                prefix = " " * pending_styled_code_indent
                markdown = "\n".join(
                    f"{prefix}{line}" if line else line for line in markdown.splitlines()
                )
            parts.append(markdown)
            pending_styled_code.clear()

    source_pages = range(section.start_page, (section.end_page or section.start_page) + 1)
    for page_number in source_pages:
        page = pages[page_number - 1]
        page_entries = [
            entry for entry in nested_entries.get(page_number, []) if entry.level > section.level
        ]
        entries_by_title = {
            " ".join(entry.title.casefold().split()): entry for entry in page_entries
        }
        block_titles = {
            " ".join((block.text or "").casefold().split())
            for block in page.blocks
            if block.type == "title"
        }
        emitted_entry_titles: set[str] = set()
        for normalized_title, entry in entries_by_title.items():
            if normalized_title not in block_titles:
                flush_styled_code()
                parts.append(f"{'#' * min(entry.level, 6)} {_escape_mdx(entry.title)}")
                emitted_entry_titles.add(normalized_title)
                previous_block_type = "title"
                previous_block = None
        section_title = " ".join(section.title.casefold().split())
        for block in page.blocks:
            styled_code = (
                block.type == "code" and bool(block.code_lines) and block.code_style is not None
            )
            if styled_code:
                if pending_styled_code and pending_styled_code[-1].code_style != block.code_style:
                    flush_styled_code()
                if not pending_styled_code:
                    pending_styled_code_indent = (
                        (list_level + 1) * 4
                        if list_base_x is not None and previous_block_type in {"list", "code"}
                        else 0
                    )
                pending_styled_code.append(block)
                previous_block_type = "code"
                previous_block = block
                continue
            flush_styled_code()
            normalized = " ".join((block.text or "").casefold().split())
            partial_section_title = (
                block.type == "title" and len(normalized) >= 8 and normalized in section_title
            )
            if normalized in entries_by_title:
                if normalized not in emitted_entry_titles:
                    entry = entries_by_title[normalized]
                    parts.append(f"{'#' * min(entry.level, 6)} {_escape_mdx(entry.title)}")
                    emitted_entry_titles.add(normalized)
                previous_block_type = "title"
                previous_block = block
                list_base_x = None
                continue
            if normalized == section_title or partial_section_title:
                continue
            if block.markdown:
                if block.type == "code" and previous_block_type == "code":
                    merged_code = _merge_fenced_code(
                        parts[-1],
                        block.markdown,
                        preserve_blank_line=_code_blocks_have_blank_line(
                            previous_block,
                            block,
                        ),
                    )
                    if merged_code is not None:
                        parts[-1] = merged_code
                        previous_block = block
                        continue
                if block.type == "list":
                    if previous_block_type not in {"list", "code"}:
                        list_base_x = block.bbox[0] if block.bbox is not None else None
                    indented = _indent_list(block.markdown, list_base_x, block)
                    if list_base_x is not None and block.bbox is not None:
                        list_level = max(
                            0,
                            round((block.bbox[0] - list_base_x) / _LIST_INDENT_POINTS),
                        )
                    if previous_block_type == "list":
                        parts[-1] = f"{parts[-1]}\n{indented}"
                        previous_block = block
                        continue
                    parts.append(indented)
                    previous_block_type = block.type
                    previous_block = block
                    continue
                if block.type == "paragraph" and previous_block_type == "paragraph":
                    combined = f"{parts[-1]}\n\n{block.markdown}"
                    dehyphenated = dehyphenate_line_breaks(combined)
                    if dehyphenated != combined:
                        parts[-1] = dehyphenated
                        previous_block = block
                        continue
                parts.append(block.markdown)
                previous_block_type = block.type
                previous_block = block
                if block.type != "code":
                    list_base_x = None
                    list_level = 0
    flush_styled_code()
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
            minimum_ratio=0,
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
