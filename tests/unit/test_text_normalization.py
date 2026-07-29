from booksite.normalize.text import dehyphenate_line_breaks, normalize_unicode


def test_normalize_unicode_uses_nfc_and_removes_invisible_noise() -> None:
    source = "cafe\u0301\u00ad\u200b α² →"

    assert normalize_unicode(source) == "café α² →"


def test_dehyphenate_joins_plain_words_split_across_lines() -> None:
    assert dehyphenate_line_breaks("an exam-\nple sentence") == "an example sentence"


def test_dehyphenate_preserves_urls_and_code_like_tokens() -> None:
    source = "https://example-\n.com\nmodel-\n_name"

    assert dehyphenate_line_breaks(source) == source

