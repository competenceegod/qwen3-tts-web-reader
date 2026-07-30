from pathlib import Path

from booksite.validate.site import _remove_generated_static_asset_copies


def test_build_cleanup_removes_only_generated_duplicate_asset_directories(
    tmp_path: Path,
) -> None:
    generated = tmp_path / "build" / "assets" / "book-id"
    generated.mkdir(parents=True)
    (generated / ".booksite-generated").write_text("hash\n", encoding="utf-8")
    (generated / "figure.png").write_bytes(b"duplicate")
    bundled = tmp_path / "build" / "assets" / "images"
    bundled.mkdir()
    (bundled / "figure-hash.png").write_bytes(b"keep")

    _remove_generated_static_asset_copies(tmp_path / "build")

    assert not generated.exists()
    assert (bundled / "figure-hash.png").read_bytes() == b"keep"
