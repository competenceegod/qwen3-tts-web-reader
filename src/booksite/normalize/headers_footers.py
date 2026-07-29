from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarginalLine:
    page_index: int
    text: str
    vertical_ratio: float


def normalize_marginal_text(text: str) -> str:
    compact = " ".join(text.casefold().split())
    if re.fullmatch(r"[\divxlcdm\-–—. ]+", compact):
        return "<page-number>"
    return compact


def find_repeated_marginal_text(
    lines: list[MarginalLine],
    page_count: int,
    minimum_ratio: float = 0.4,
) -> set[str]:
    """Return normalized strings repeated in the top or bottom 10% of pages."""
    pages_by_text: dict[str, set[int]] = defaultdict(set)
    for line in lines:
        if line.vertical_ratio > 0.1 and line.vertical_ratio < 0.9:
            continue
        normalized = normalize_marginal_text(line.text)
        if normalized:
            pages_by_text[normalized].add(line.page_index)

    minimum_pages = max(2, round(page_count * minimum_ratio))
    return {
        text for text, page_indexes in pages_by_text.items() if len(page_indexes) >= minimum_pages
    }
