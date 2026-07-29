from pathlib import Path

from booksite.utils.cache import CacheStore, build_cache_key


def test_cache_store_round_trips_json_atomically(tmp_path: Path) -> None:
    cache = CacheStore(tmp_path)

    cache.write_json("book-1", "audit", {"complete": True, "pages": 2})

    assert cache.read_json("book-1", "audit") == {"complete": True, "pages": 2}
    assert not list(tmp_path.rglob("*.tmp"))


def test_cache_key_changes_with_page_or_config() -> None:
    base = build_cache_key("abc", page_index=1, config={"ocr": False}, engine="native")

    assert base != build_cache_key("abc", 2, {"ocr": False}, "native")
    assert base != build_cache_key("abc", 1, {"ocr": True}, "native")
