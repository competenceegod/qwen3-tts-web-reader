from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pymupdf

from booksite.models.book_ir import AssetIR, BlockIR, BookIR
from booksite.utils.cache import atomic_write_bytes, atomic_write_text


def _media_type(extension: str) -> str:
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "jp2": "image/jp2",
    }.get(extension.casefold(), f"image/{extension.casefold()}")


def _browser_compatible_image(content: bytes, extension: str) -> tuple[bytes, str]:
    supported = {"gif", "jpg", "jpeg", "png", "svg", "webp"}
    if extension.casefold() in supported:
        return content, extension.casefold()
    pixmap = pymupdf.Pixmap(content)
    if pixmap.colorspace and pixmap.colorspace.n > 3:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
    return pixmap.tobytes("png"), "png"


def _add_asset_markdown(book: BookIR, asset: AssetIR) -> None:
    page_index = asset.source_page - 1
    block = BlockIR(
        block_id=f"p{asset.source_page:04d}-asset-{asset.asset_id[-8:]}",
        page_index=page_index,
        order=len(book.pages[page_index].blocks),
        type="image",
        asset_path=asset.path,
        markdown=f"![Figure from PDF page {asset.source_page}]({asset.path})",
        source_engine="native",
        confidence=1.0,
    )
    book.pages[page_index].blocks.append(block)
    for section in book.sections:
        if asset.source_page not in section.source_pages:
            continue
        marker_position = section.markdown.rfind("\n\n*PDF page")
        insertion = f"\n\n{block.markdown}"
        if marker_position >= 0:
            section.markdown = (
                section.markdown[:marker_position] + insertion + section.markdown[marker_position:]
            )
        else:
            section.markdown = section.markdown.rstrip() + insertion + "\n"
        break


def extract_native_assets(
    pdf_path: str | Path,
    book: BookIR,
    static_dir: str | Path,
    fallback_dpi: int = 180,
) -> list[AssetIR]:
    """Extract embedded images and render contentless pages as local fallbacks."""
    assets_root = Path(static_dir) / "assets"
    assets_root.mkdir(parents=True, exist_ok=True)
    target_root = assets_root / book.book_id
    for previous_root in assets_root.iterdir():
        if (
            previous_root != target_root
            and previous_root.is_dir()
            and (previous_root / ".booksite-generated").exists()
        ):
            shutil.rmtree(previous_root)
    target_root.mkdir(parents=True, exist_ok=True)
    for stale_asset in target_root.iterdir():
        if stale_asset.is_file():
            stale_asset.unlink()
    atomic_write_text(target_root / ".booksite-generated", f"{book.source_sha256}\n")
    assets: list[AssetIR] = []
    stored_images: dict[str, tuple[str, str]] = {}

    with pymupdf.open(pdf_path) as document:
        for page_index in range(book.page_count):
            page = document[page_index]
            page_assets = 0
            for figure_index, image in enumerate(page.get_images(full=True), start=1):
                extracted = document.extract_image(int(image[0]))
                content, extension = _browser_compatible_image(
                    extracted["image"],
                    str(extracted.get("ext") or "png"),
                )
                digest = hashlib.sha256(content).hexdigest()
                if digest in stored_images:
                    asset_path, media_type = stored_images[digest]
                else:
                    filename = (
                        f"p{page_index + 1:04d}-figure-{figure_index:02d}-{digest[:8]}.{extension}"
                    )
                    file_path = target_root / filename
                    atomic_write_bytes(file_path, content)
                    asset_path = f"/assets/{book.book_id}/{filename}"
                    media_type = _media_type(extension)
                    stored_images[digest] = (asset_path, media_type)
                asset = AssetIR(
                    asset_id=(f"image-{digest[:12]}-p{page_index + 1:04d}-f{figure_index:02d}"),
                    source_page=page_index + 1,
                    path=asset_path,
                    sha256=digest,
                    media_type=media_type,
                )
                assets.append(asset)
                _add_asset_markdown(book, asset)
                page_assets += 1

            if book.pages[page_index].native_text_char_count > 0 or page_assets:
                continue
            scale = fallback_dpi / 72
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            content = pixmap.tobytes("png")
            digest = hashlib.sha256(content).hexdigest()
            filename = f"p{page_index + 1:04d}-page-fallback-{digest[:8]}.png"
            atomic_write_bytes(target_root / filename, content)
            asset = AssetIR(
                asset_id=f"page-{digest[:16]}",
                source_page=page_index + 1,
                path=f"/assets/{book.book_id}/{filename}",
                sha256=digest,
                media_type="image/png",
            )
            assets.append(asset)
            _add_asset_markdown(book, asset)

    book.assets = assets
    return assets
