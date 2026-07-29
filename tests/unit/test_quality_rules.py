from booksite.quality.rules import NativeTextStatus, classify_native_text


def test_classifies_good_native_text() -> None:
    text = "A reliable paragraph with embedded text. " * 5

    assert classify_native_text(text, image_coverage_ratio=0.0) is NativeTextStatus.TEXT_GOOD


def test_classifies_image_only_page() -> None:
    assert classify_native_text("", image_coverage_ratio=0.8) is NativeTextStatus.IMAGE_ONLY


def test_classifies_short_native_text_as_suspect() -> None:
    assert (
        classify_native_text("Short but present text.", image_coverage_ratio=0.0)
        is NativeTextStatus.TEXT_SUSPECT
    )

