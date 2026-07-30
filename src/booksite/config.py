from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    language: str = "auto"
    output_format: str = "docusaurus"
    local_only: bool = True


class RuntimeConfig(BaseModel):
    max_core_workers: int = Field(default=2, ge=1, le=8)
    render_workers: int = Field(default=4, ge=1, le=8)
    model_workers: int = Field(default=1, ge=1, le=1)
    resume: bool = True


class PdfConfig(BaseModel):
    render_dpi: int = Field(default=200, ge=72, le=600)
    fallback_render_dpi: int = Field(default=250, ge=72, le=600)
    unicode_normalization: str = "NFC"


class DoclingConfig(BaseModel):
    enabled: bool = True
    ocr: bool = False
    table_structure: bool = True
    formula_enrichment: bool = True
    picture_images: bool = True
    code_enrichment: bool = True
    force_backend_text: bool = True


class ExternalEngineConfig(BaseModel):
    enabled: bool = False
    executable: str
    timeout_seconds_per_page: int = Field(default=180, ge=1)


class MineruConfig(ExternalEngineConfig):
    executable: str = ".venv-mineru/bin/mineru"
    backend: str = "pipeline"


class Ovisocr2Config(ExternalEngineConfig):
    executable: str = ".venv-ovis/bin/ovisocr2-parse"
    model_id: str = ""
    quantization: str = "4bit"
    max_tokens: int = Field(default=8192, ge=1)
    temperature: float = Field(default=0, ge=0, le=2)


class QualityConfig(BaseModel):
    fallback_threshold: float = Field(default=0.72, ge=0, le=1)
    minimum_text_recall: float = Field(default=0.85, ge=0, le=1)
    maximum_replacement_ratio: float = Field(default=0.005, ge=0, le=1)
    maximum_fragmented_line_ratio: float = Field(default=0.15, ge=0, le=1)


class AssemblyConfig(BaseModel):
    max_words_per_page: int = Field(default=20_000, ge=100)
    max_headings_per_page: int = Field(default=40, ge=1)
    merge_cross_page_paragraphs: bool = True
    remove_repeated_headers: bool = True
    remove_repeated_footers: bool = True


class SiteConfig(BaseModel):
    title_from_pdf: bool = True
    toc_min_heading_level: int = Field(default=2, ge=2, le=6)
    toc_max_heading_level: int = Field(default=5, ge=2, le=6)
    base_url: str = "/"
    offline_assets: bool = True


class PipelineConfig(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    pdf: PdfConfig = Field(default_factory=PdfConfig)
    docling: DoclingConfig = Field(default_factory=DoclingConfig)
    mineru: MineruConfig = Field(default_factory=MineruConfig)
    ovisocr2: Ovisocr2Config = Field(default_factory=Ovisocr2Config)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    assembly: AssemblyConfig = Field(default_factory=AssemblyConfig)
    site: SiteConfig = Field(default_factory=SiteConfig)

    def unsupported_non_default_options(self) -> list[str]:
        """Return configured options that this release does not execute."""
        current = self.model_dump(mode="python")
        defaults = type(self)().model_dump(mode="python")
        operational = {
            "pdf.fallback_render_dpi",
            *(f"docling.{name}" for name in current["docling"]),
        }
        changed: list[str] = []
        for section, values in current.items():
            for name, value in values.items():
                option = f"{section}.{name}"
                if option not in operational and value != defaults[section][name]:
                    changed.append(option)
        return sorted(changed)


_ENV_REFERENCE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-(.*?))?\}")


def _expand_environment(value: object) -> object:
    if isinstance(value, str):
        return _ENV_REFERENCE.sub(
            lambda match: os.environ.get(match.group(1), match.group(2) or ""),
            value,
        )
    if isinstance(value, list):
        return [_expand_environment(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_environment(item) for key, item in value.items()}
    return value


def load_config(path: str | Path | None = None) -> PipelineConfig:
    if path is None:
        return PipelineConfig()
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return PipelineConfig.model_validate(_expand_environment(raw))
