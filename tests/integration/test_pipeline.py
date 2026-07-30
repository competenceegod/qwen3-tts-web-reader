from pathlib import Path

import pymupdf

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
            "quality": {"fallback_threshold": 0.8},
        }
    )
    changed_result = PipelineRunner(
        changed_config,
        workspace_root=tmp_path / "workspace",
    ).run_all(pdf_path, tmp_path / "site", build_site=False)

    assert changed_result.used_cached_audit is False
    assert changed_result.used_cached_assembly is False


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
