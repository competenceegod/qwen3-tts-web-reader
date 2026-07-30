from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from booksite.assemble.native import assemble_native_book
from booksite.config import PipelineConfig
from booksite.engines.docling_engine import convert_with_docling
from booksite.models.book_ir import BookIR, WarningIR
from booksite.models.reports import AuditReport
from booksite.pdf.audit import audit_pdf, book_id_for_source
from booksite.reporting import write_quality_report
from booksite.site.assets import extract_native_assets
from booksite.site.docusaurus import generate_docusaurus_site
from booksite.utils.cache import CacheStore, atomic_write_text
from booksite.validate.site import build_docusaurus, validate_content

_CACHE_SCHEMA_VERSION = "native-book-ir-v6"
_SITE_MANIFEST = ".booksite-site.json"
_LEGACY_SITE_MARKERS = (
    "build",
    "docs",
    "docusaurus.config.js",
    "docusaurus.config.mjs",
    "package.json",
)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    book_id: str
    site_dir: Path
    audit_path: Path
    book_ir_path: Path
    summary_path: Path
    quality_report_path: Path
    build_log_path: Path | None
    used_cached_audit: bool
    used_cached_assembly: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cached_identity_matches(
    cached: dict[str, object] | None,
    *,
    book_id: str,
    source_hash: str,
    source: Path,
) -> bool:
    if not cached:
        return False
    try:
        cached_source = Path(str(cached.get("source_pdf", ""))).expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    return (
        cached.get("book_id") == book_id
        and cached.get("source_sha256") == source_hash
        and cached_source == source
    )


def _prepare_output_root(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    legacy_markers = [name for name in _LEGACY_SITE_MARKERS if (output_root / name).exists()]
    if legacy_markers:
        joined = ", ".join(legacy_markers)
        raise RuntimeError(
            "The output root contains a legacy flat Docusaurus site "
            f"({joined}). Move it aside, then rerun so books can be isolated."
        )


def _validate_existing_site(target: Path, book: BookIR) -> None:
    if target.is_symlink():
        raise RuntimeError(f"Refusing symbolic link as generated site target: {target}")
    if not target.exists():
        return
    if not target.is_dir():
        raise RuntimeError(f"Generated site target is not a directory: {target}")

    manifest_path = target / _SITE_MANIFEST
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise RuntimeError(f"Invalid site ownership manifest: {manifest_path}") from error
        if not isinstance(manifest, dict):
            raise RuntimeError(f"Invalid site ownership manifest: {manifest_path}")
        if (
            manifest.get("book_id") != book.book_id
            or manifest.get("source_sha256") != book.source_sha256
        ):
            raise RuntimeError(f"Site directory belongs to a different source PDF: {target}")
        return

    legacy_owner = target / "static" / "assets" / book.book_id / ".booksite-generated"
    if legacy_owner.exists() and legacy_owner.read_text(encoding="utf-8").strip() == (
        book.source_sha256
    ):
        return
    if any(target.iterdir()):
        raise RuntimeError(f"Site directory has no trusted ownership manifest: {target}")


def _write_site_manifest(target: Path, book: BookIR) -> None:
    atomic_write_text(
        target / _SITE_MANIFEST,
        json.dumps(
            {
                "schema_version": 1,
                "book_id": book.book_id,
                "source_pdf": str(book.source_pdf),
                "source_sha256": book.source_sha256,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )


def _promote_site(staging: Path, target: Path) -> None:
    backup: Path | None = None
    if target.exists():
        backup = target.parent / f".{target.name}.backup-{uuid.uuid4().hex}"
        os.replace(target, backup)
    try:
        os.replace(staging, target)
    except Exception:
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup is not None:
        shutil.rmtree(backup)


class PipelineRunner:
    def __init__(
        self,
        config: PipelineConfig,
        workspace_root: str | Path = "workspace",
    ) -> None:
        unsupported = config.unsupported_non_default_options()
        if unsupported:
            raise ValueError("Unsupported non-default options: " + ", ".join(unsupported))
        self.config = config
        self.workspace_root = Path(workspace_root)
        self.cache = CacheStore(self.workspace_root / "cache")
        serialized_config = json.dumps(
            {
                "cache_schema_version": _CACHE_SCHEMA_VERSION,
                "config": config.model_dump(mode="json"),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        self.config_fingerprint = hashlib.sha256(serialized_config).hexdigest()[:12]

    def _identity(self, pdf_path: Path) -> tuple[str, str]:
        source_hash = _sha256(pdf_path)
        return book_id_for_source(pdf_path, source_hash), source_hash

    def audit(
        self,
        pdf_path: str | Path,
        max_pages: int | None = None,
        force: bool = False,
    ) -> tuple[AuditReport, Path, bool]:
        source = Path(pdf_path).expanduser().resolve()
        book_id, source_hash = self._identity(source)
        stage = f"audit-pages-{max_pages or 'all'}-{self.config_fingerprint}"
        cached = None if force else self.cache.read_json(book_id, stage)
        used_cache = _cached_identity_matches(
            cached,
            book_id=book_id,
            source_hash=source_hash,
            source=source,
        )
        report = AuditReport.model_validate(cached) if used_cache else audit_pdf(source, max_pages)
        if not used_cache:
            self.cache.write_json(book_id, stage, report.model_dump(mode="json"))
        intermediate_path = self.workspace_root / "intermediate" / book_id / "audit.json"
        atomic_write_text(
            intermediate_path,
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        )
        return report, intermediate_path, used_cache

    def assemble(
        self,
        pdf_path: str | Path,
        audit: AuditReport,
        max_pages: int | None = None,
        force: bool = False,
    ) -> tuple[BookIR, bool]:
        stage = f"assemble-pages-{max_pages or 'all'}-{self.config_fingerprint}"
        cached = None if force else self.cache.read_json(audit.book_id, stage)
        source = Path(pdf_path).expanduser().resolve()
        used_cache = _cached_identity_matches(
            cached,
            book_id=audit.book_id,
            source_hash=audit.source_sha256,
            source=source,
        )
        book = (
            BookIR.model_validate(cached) if used_cache else assemble_native_book(pdf_path, audit)
        )
        if not used_cache:
            self.cache.write_json(audit.book_id, stage, book.model_dump(mode="json"))
        return book, used_cache

    def run_all(
        self,
        pdf_path: str | Path,
        site_dir: str | Path,
        max_pages: int | None = None,
        build_site: bool = True,
        force_page: int | None = None,
    ) -> PipelineResult:
        source = Path(pdf_path).expanduser().resolve()
        force = force_page is not None
        audit, audit_path, used_cached_audit = self.audit(source, max_pages, force=force)
        current_hash = _sha256(source)
        expected_book_id = book_id_for_source(source, current_hash)
        if (
            audit.source_sha256 != current_hash
            or audit.book_id != expected_book_id
            or audit.source_pdf.resolve() != source
        ):
            raise RuntimeError("PDF identity changed or audit identity is invalid")
        if force_page is not None and not 1 <= force_page <= audit.page_count:
            raise ValueError(f"--force-page must be between 1 and {audit.page_count}")
        book, used_cached_assembly = self.assemble(source, audit, max_pages, force=force)
        if (
            book.book_id != expected_book_id
            or book.source_sha256 != current_hash
            or book.source_pdf.resolve() != source
        ):
            raise RuntimeError("Assembled book identity does not match the source PDF")
        if self.config.docling.enabled:
            docling_dir = self.workspace_root / "intermediate" / book.book_id / "docling"
            try:
                convert_with_docling(source, docling_dir, self.config.docling, max_pages)
                book.engine_versions["docling"] = "2.116.0"
            except RuntimeError as error:
                book.warnings.append(
                    WarningIR(
                        code="docling_unavailable",
                        message=str(error),
                        severity="info",
                    )
                )

        output_root = Path(site_dir).expanduser().resolve()
        _prepare_output_root(output_root)
        target_site = output_root / book.book_id
        if not target_site.absolute().is_relative_to(output_root):
            raise RuntimeError(f"Generated site target escapes the output root: {target_site}")
        _validate_existing_site(target_site, book)
        staging_site = Path(
            tempfile.mkdtemp(
                prefix=f".{book.book_id}.staging-",
                dir=output_root,
            )
        )

        intermediate_dir = self.workspace_root / "intermediate" / book.book_id
        try:
            extract_native_assets(
                source,
                book,
                staging_site / "static",
                fallback_dpi=self.config.pdf.fallback_render_dpi,
            )
            generate_docusaurus_site(book, staging_site)
            _write_site_manifest(staging_site, book)

            book_ir_path = intermediate_dir / "book-ir.json"
            atomic_write_text(
                book_ir_path,
                json.dumps(book.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            )
            report_paths = write_quality_report(
                book,
                self.workspace_root / "reports" / book.book_id,
            )
            static_report = staging_site / "static" / "quality-report.html"
            static_report.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(report_paths.html, static_report)

            validation = validate_content(book, staging_site)
            if not validation.ok:
                raise RuntimeError("; ".join(validation.errors))
            build_log = None
            if build_site:
                build_log = build_docusaurus(
                    staging_site,
                    self.workspace_root / "reports" / book.book_id,
                )
            _promote_site(staging_site, target_site)
        except Exception:
            if staging_site.exists():
                shutil.rmtree(staging_site)
            raise
        return PipelineResult(
            book_id=book.book_id,
            site_dir=target_site,
            audit_path=audit_path,
            book_ir_path=book_ir_path,
            summary_path=report_paths.summary,
            quality_report_path=report_paths.html,
            build_log_path=build_log,
            used_cached_audit=used_cached_audit,
            used_cached_assembly=used_cached_assembly,
        )
