from booksite.assemble.slugger import stable_slug


def test_stable_slug_is_readable_and_deterministic() -> None:
    first = stable_slug("Chapter 1 — Introduction", source_page=23)
    second = stable_slug("Chapter 1 — Introduction", source_page=23)

    assert first == second
    assert first.startswith("chapter-1-introduction-")
    assert len(first.rsplit("-", 1)[-1]) == 8


def test_stable_slug_changes_when_source_page_changes() -> None:
    assert stable_slug("Introduction", 1) != stable_slug("Introduction", 2)
