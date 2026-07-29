from pathlib import Path

import pymupdf

from booksite.config import PipelineConfig
from booksite.pipeline import PipelineRunner


def test_pipeline_creates_cached_ir_report_and_site(tmp_path: Path) -> None:
    pdf_path = tmp_path / "input.pdf"
    document = pymupdf.open()
    page = document.new_page(width=400, height=600)
    page.insert_text((30, 80), "A Test Book", fontsize=22)
    page.insert_text((30, 140), "Readable local content. " * 12, fontsize=11)
    document.set_toc([[1, "A Test Book", 1]])
    document.save(pdf_path)
    document.close()

    config = PipelineConfig.model_validate({"docling": {"enabled": False}})
    runner = PipelineRunner(config, workspace_root=tmp_path / "workspace")
    result = runner.run_all(pdf_path, site_dir=tmp_path / "site", build_site=False)

    assert result.audit_path.exists()
    assert result.book_ir_path.exists()
    assert result.summary_path.exists()
    assert result.quality_report_path.exists()
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
