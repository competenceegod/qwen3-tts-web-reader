from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from booksite.config import DoclingConfig
from booksite.utils.cache import atomic_write_text


@dataclass(frozen=True, slots=True)
class DoclingArtifacts:
    json_path: Path
    markdown_path: Path
    html_path: Path


def convert_with_docling(
    pdf_path: str | Path,
    output_dir: str | Path,
    config: DoclingConfig,
    max_pages: int | None = None,
) -> DoclingArtifacts:
    """Run the current documented Docling PDF pipeline entirely locally."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as error:
        raise RuntimeError(
            "Docling is not installed; install the optional dependency with "
            "`uv sync --extra docling`"
        ) from error

    options = PdfPipelineOptions(
        do_ocr=config.ocr,
        do_table_structure=config.table_structure,
    )
    options.do_formula_enrichment = config.formula_enrichment
    options.do_code_enrichment = config.code_enrichment
    options.generate_picture_images = config.picture_images
    options.force_backend_text = config.force_backend_text
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    conversion = converter.convert(
        Path(pdf_path),
        **({"max_num_pages": max_pages} if max_pages else {}),
    )
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "document.json"
    markdown_path = target / "document.md"
    html_path = target / "document.html"
    atomic_write_text(
        json_path,
        json.dumps(conversion.document.export_to_dict(), ensure_ascii=False, indent=2) + "\n",
    )
    atomic_write_text(markdown_path, conversion.document.export_to_markdown())
    atomic_write_text(html_path, conversion.document.export_to_html())
    return DoclingArtifacts(json_path, markdown_path, html_path)
