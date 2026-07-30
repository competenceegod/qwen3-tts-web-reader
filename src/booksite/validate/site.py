from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from booksite.models.book_ir import BookIR

_IMAGE_REFERENCE = re.compile(r"!\[[^\]]*]\((/assets/[^)]+)\)")


@dataclass(slots=True)
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    build_log: Path | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_content(book: BookIR, site_dir: str | Path) -> ValidationResult:
    target = Path(site_dir)
    result = ValidationResult()
    ids = [section.section_id for section in book.sections]
    slugs = [section.slug for section in book.sections]
    if len(ids) != len(set(ids)):
        result.errors.append("Duplicate document IDs")
    if len(slugs) != len(set(slugs)):
        result.errors.append("Duplicate document slugs")
    covered_pages = {page for section in book.sections for page in section.source_pages}
    missing_pages = set(range(1, book.page_count + 1)) - covered_pages
    if missing_pages:
        result.errors.append(f"Pages missing from sections: {sorted(missing_pages)}")
    for section in book.sections:
        for reference in _IMAGE_REFERENCE.findall(section.markdown):
            if not (target / "static" / reference.lstrip("/")).exists():
                result.errors.append(f"Missing image: {reference}")
    if not list((target / "docs").glob("*.md")):
        result.errors.append("No generated Docusaurus documents")
    return result


def _remove_generated_static_asset_copies(build_dir: Path) -> None:
    assets_dir = build_dir / "assets"
    if not assets_dir.is_dir():
        return
    for candidate in assets_dir.iterdir():
        if candidate.is_dir() and (candidate / ".booksite-generated").is_file():
            shutil.rmtree(candidate)


def build_docusaurus(site_dir: str | Path, log_dir: str | Path) -> Path:
    target = Path(site_dir)
    logs = Path(log_dir)
    logs.mkdir(parents=True, exist_ok=True)
    pnpm = os.environ.get("BOOKSITE_PNPM") or shutil.which("pnpm")
    if not pnpm:
        raise RuntimeError("pnpm was not found; set BOOKSITE_PNPM or install pnpm")
    install_command = [pnpm, "install"]
    if (target / "pnpm-lock.yaml").exists():
        install_command.append("--frozen-lockfile")
    install = subprocess.run(
        install_command,
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
    )
    build = subprocess.run(
        [pnpm, "build"],
        cwd=target,
        capture_output=True,
        text=True,
        check=False,
    )
    log_path = logs / "docusaurus-build.log"
    log_path.write_text(
        "INSTALL STDOUT\n"
        + install.stdout
        + "\nINSTALL STDERR\n"
        + install.stderr
        + "\nBUILD STDOUT\n"
        + build.stdout
        + "\nBUILD STDERR\n"
        + build.stderr,
        encoding="utf-8",
    )
    if install.returncode or build.returncode:
        raise RuntimeError(f"Docusaurus build failed; see {log_path}")
    _remove_generated_static_asset_copies(target / "build")
    return log_path
