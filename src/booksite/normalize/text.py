from __future__ import annotations

import re
import unicodedata

_INVISIBLE_NOISE = str.maketrans("", "", "\u00ad\u200b\u200c\u200d\ufeff")
_PLAIN_LINE_BREAK = re.compile(r"(?<![/\w.-])([A-Za-z]{2,})-\n([a-z][A-Za-z]{1,})")


def normalize_unicode(text: str) -> str:
    """Apply NFC and remove copy artifacts without changing math symbols."""
    return unicodedata.normalize("NFC", text.translate(_INVISIBLE_NOISE))


def dehyphenate_line_breaks(text: str) -> str:
    """Conservatively join plain alphabetic words split at a line boundary."""
    return _PLAIN_LINE_BREAK.sub(lambda match: f"{match.group(1)}{match.group(2)}", text)

