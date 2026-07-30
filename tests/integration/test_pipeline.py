import hashlib
import json
from pathlib import Path

import pymupdf
import pytest

from booksite.config import PipelineConfig
from booksite.pipeline import PipelineRunner


def _write_test_pdf(path: Path, title: str) -> None:
    document = pymupdf.open()
    page = document.new_page(width=400, height=600)
    page.insert_text((30, 80), title, fontsize=22)
    page.insert_text((30, 140), "Readable local content. " * 12, fontsize=11)
    document.set_toc([[1, title, 1]])
    document.save(path)
    document.close()


def test_pipeline_creates_cached_ir_report_and_site(tmp_path: Path) -> None:
    pdf_path = tmp_path / "input.pdf"
    _write_test_pdf(pdf_path, "A Test Book")

    config = PipelineConfig.model_validate({"docling": {"enabled": False}})
    runner = PipelineRunner(config, workspace_root=tmp_path / "workspace")
    result = runner.run_all(pdf_path, site_dir=tmp_path / "site", build_site=False)

    assert result.audit_path.exists()
    assert result.book_ir_path.exists()
    assert result.summary_path.exists()
    assert result.quality_report_path.exists()
    assert result.site_dir == (tmp_path / "site" / result.book_id).resolve()
    assert (result.site_dir / "docs").exists()
    assert (result.site_dir / "static" / "quality-report.html").exists()
    assert runner.run_all(pdf_path, tmp_path / "site", build_site=False).used_cached_audit

    changed_config = PipelineConfig.model_validate(
        {
            "docling": {"enabled": False},
            "pdf": {"fallback_render_dpi": 300},
        }
    )
    changed_result = PipelineRunner(
        changed_config,
        workspace_root=tmp_path / "workspace",
    ).run_all(pdf_path, tmp_path / "site", build_site=False)

    assert changed_result.used_cached_audit is False
    assert changed_result.used_cached_assembly is False


def test_pipeline_does_not_reuse_native_book_ir_v5_cache(tmp_path: Path) -> None:
    pdf_path = tmp_path / "input.pdf"
    _write_test_pdf(pdf_path, "A Test Book")
    config = PipelineConfig.model_validate({"docling": {"enabled": False}})
    runner = PipelineRunner(config, workspace_root=tmp_path / "workspace")
    report, _, _ = runner.audit(pdf_path)
    fresh_book, _ = runner.assemble(pdf_path, report, force=True)
    current_stage = f"assemble-pages-all-{runner.config_fingerprint}"
    runner.cache.stage_path(report.book_id, current_stage).unlink()

    legacy_config = json.dumps(
        {
            "cache_schema_version": "native-book-ir-v5",
            "config": config.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    legacy_fingerprint = hashlib.sha256(legacy_config).hexdigest()[:12]
    legacy_stage = f"assemble-pages-all-{legacy_fingerprint}"
    stale_book = fresh_book.model_copy(update={"title": "STALE V5 BOOK"})
    runner.cache.write_json(
        report.book_id,
        legacy_stage,
        stale_book.model_dump(mode="json"),
    )

    rebuilt_book, used_cache = runner.assemble(pdf_path, report)

    assert used_cache is False
    assert rebuilt_book.title == "A Test Book"


def test_runner_rejects_non_default_options_that_are_not_implemented(
    tmp_path: Path,
) -> None:
    config = PipelineConfig.model_validate(
        {
            "docling": {"enabled": False},
            "site": {"base_url": "/books/"},
        }
    )

    with pytest.raises(ValueError, match=r"Unsupported non-default options: site\.base_url"):
        PipelineRunner(config, workspace_root=tmp_path / "workspace")


def test_pipeline_keeps_different_pdfs_in_separate_site_directories(tmp_path: Path) -> None:
    first_pdf = tmp_path / "First Guide.pdf"
    second_pdf = tmp_path / "Second Guide.pdf"
    _write_test_pdf(first_pdf, "First Guide")
    _write_test_pdf(second_pdf, "Second Guide")

    output_root = tmp_path / "site"
    runner = PipelineRunner(
        PipelineConfig.model_validate({"docling": {"enabled": False}}),
        workspace_root=tmp_path / "workspace",
    )
    first = runner.run_all(first_pdf, site_dir=output_root, build_site=False)
    first_marker = first.site_dir / "first-site-marker.txt"
    first_marker.write_text("preserve me", encoding="utf-8")

    second = runner.run_all(second_pdf, site_dir=output_root, build_site=False)

    assert first.site_dir == output_root.resolve() / first.book_id
    assert second.site_dir == output_root.resolve() / second.book_id
    assert first.site_dir != second.site_dir
    assert first_marker.read_text(encoding="utf-8") == "preserve me"
    assert (first.site_dir / "docs").is_dir()
    assert (second.site_dir / "docs").is_dir()


def test_pipeline_separates_same_named_pdfs_with_different_content(
    tmp_path: Path,
) -> None:
    first_pdf = tmp_path / "first" / "Shared Guide.pdf"
    second_pdf = tmp_path / "second" / "Shared Guide.pdf"
    first_pdf.parent.mkdir()
    second_pdf.parent.mkdir()
    _write_test_pdf(first_pdf, "First Shared Guide")
    _write_test_pdf(second_pdf, "Second Shared Guide")
    runner = PipelineRunner(
        PipelineConfig.model_validate({"docling": {"enabled": False}}),
        workspace_root=tmp_path / "workspace",
    )

    first = runner.run_all(first_pdf, tmp_path / "site", build_site=False)
    second = runner.run_all(second_pdf, tmp_path / "site", build_site=False)

    assert first.book_id != second.book_id
    assert first.site_dir.name.startswith("shared-guide-")
    assert second.site_dir.name.startswith("shared-guide-")
    assert first.site_dir.is_dir()
    assert second.site_dir.is_dir()


def test_pipeline_rejects_symlinked_book_target(tmp_path: Path) -> None:
    pdf_path = tmp_path / "input.pdf"
    _write_test_pdf(pdf_path, "A Test Book")
    output_root = tmp_path / "site"
    outside = tmp_path / "outside"
    outside.mkdir()
    runner = PipelineRunner(
        PipelineConfig.model_validate({"docling": {"enabled": False}}),
        workspace_root=tmp_path / "workspace",
    )
    book_id, _ = runner._identity(pdf_path.resolve())
    output_root.mkdir()
    (output_root / book_id).symlink_to(outside, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symbolic link"):
        runner.run_all(pdf_path, output_root, build_site=False)

    assert list(outside.iterdir()) == []


def test_pipeline_ignores_cache_with_poisoned_book_id(tmp_path: Path) -> None:
    pdf_path = tmp_path / "input.pdf"
    _write_test_pdf(pdf_path, "A Test Book")
    runner = PipelineRunner(
        PipelineConfig.model_validate({"docling": {"enabled": False}}),
        workspace_root=tmp_path / "workspace",
    )
    report, _, _ = runner.audit(pdf_path)
    stage = f"audit-pages-all-{runner.config_fingerprint}"
    cache_path = runner.cache.stage_path(report.book_id, stage)
    poisoned = json.loads(cache_path.read_text(encoding="utf-8"))
    poisoned["book_id"] = "../../outside"
    cache_path.write_text(json.dumps(poisoned), encoding="utf-8")

    refreshed, _, used_cache = runner.audit(pdf_path)

    assert used_cache is False
    assert refreshed.book_id == report.book_id


def test_pipeline_rejects_legacy_flat_site_root(tmp_path: Path) -> None:
    pdf_path = tmp_path / "input.pdf"
    _write_test_pdf(pdf_path, "A Test Book")
    output_root = tmp_path / "site"
    (output_root / "docs").mkdir(parents=True)
    (output_root / "package.json").write_text("{}\n", encoding="utf-8")
    runner = PipelineRunner(
        PipelineConfig.model_validate({"docling": {"enabled": False}}),
        workspace_root=tmp_path / "workspace",
    )

    with pytest.raises(RuntimeError, match="legacy flat Docusaurus site"):
        runner.run_all(pdf_path, output_root, build_site=False)


def test_pipeline_rejects_book_id_collision_using_full_hash_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_pdf = tmp_path / "First.pdf"
    second_pdf = tmp_path / "Second.pdf"
    _write_test_pdf(first_pdf, "First")
    _write_test_pdf(second_pdf, "Second")
    runner = PipelineRunner(
        PipelineConfig.model_validate({"docling": {"enabled": False}}),
        workspace_root=tmp_path / "workspace",
    )
    monkeypatch.setattr("booksite.pipeline.book_id_for_source", lambda *_: "forced-id")
    monkeypatch.setattr("booksite.pdf.audit.book_id_for_source", lambda *_: "forced-id")
    output_root = tmp_path / "site"

    first = runner.run_all(first_pdf, output_root, build_site=False)

    with pytest.raises(RuntimeError, match="different source PDF"):
        runner.run_all(second_pdf, output_root, build_site=False)

    manifest = json.loads((first.site_dir / ".booksite-site.json").read_text(encoding="utf-8"))
    assert manifest["source_sha256"] == hashlib.sha256(first_pdf.read_bytes()).hexdigest()


def test_pipeline_rejects_non_object_site_manifest(tmp_path: Path) -> None:
    pdf_path = tmp_path / "input.pdf"
    _write_test_pdf(pdf_path, "A Test Book")
    runner = PipelineRunner(
        PipelineConfig.model_validate({"docling": {"enabled": False}}),
        workspace_root=tmp_path / "workspace",
    )
    first = runner.run_all(pdf_path, tmp_path / "site", build_site=False)
    (first.site_dir / ".booksite-site.json").write_text("[]\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Invalid site ownership manifest"):
        runner.run_all(pdf_path, tmp_path / "site", build_site=False)


def test_failed_regeneration_preserves_previous_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "input.pdf"
    _write_test_pdf(pdf_path, "A Test Book")
    runner = PipelineRunner(
        PipelineConfig.model_validate({"docling": {"enabled": False}}),
        workspace_root=tmp_path / "workspace",
    )
    first = runner.run_all(pdf_path, tmp_path / "site", build_site=False)
    existing_doc = next((first.site_dir / "docs").glob("*.md"))
    original = existing_doc.read_text(encoding="utf-8")

    def fail_generation(book: object, site_dir: str | Path) -> None:
        damaged = Path(site_dir) / "docs"
        damaged.mkdir(parents=True, exist_ok=True)
        (damaged / existing_doc.name).write_text("damaged", encoding="utf-8")
        raise RuntimeError("synthetic generation failure")

    monkeypatch.setattr("booksite.pipeline.generate_docusaurus_site", fail_generation)

    with pytest.raises(RuntimeError, match="synthetic generation failure"):
        runner.run_all(pdf_path, tmp_path / "site", build_site=False)

    assert existing_doc.read_text(encoding="utf-8") == original


def test_no_build_regeneration_does_not_leave_stale_build(tmp_path: Path) -> None:
    pdf_path = tmp_path / "input.pdf"
    _write_test_pdf(pdf_path, "A Test Book")
    runner = PipelineRunner(
        PipelineConfig.model_validate({"docling": {"enabled": False}}),
        workspace_root=tmp_path / "workspace",
    )
    first = runner.run_all(pdf_path, tmp_path / "site", build_site=False)
    stale_index = first.site_dir / "build" / "index.html"
    stale_index.parent.mkdir()
    stale_index.write_text("stale", encoding="utf-8")

    refreshed = runner.run_all(pdf_path, tmp_path / "site", build_site=False)

    assert not (refreshed.site_dir / "build").exists()
