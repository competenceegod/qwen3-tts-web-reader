from __future__ import annotations

import hashlib
import re
import unicodedata


def _readable_title(title: str) -> str:
    decomposed = unicodedata.normalize("NFKD", title)
    ascii_title = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return slug or "section"


def stable_slug(title: str, source_page: int) -> str:
    """Create a readable slug whose suffix is stable for the source location."""
    digest = hashlib.sha256(f"{source_page}:{title}".encode()).hexdigest()[:8]
    return f"{_readable_title(title)}-{digest}"
