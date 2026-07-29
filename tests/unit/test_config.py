from pathlib import Path

from booksite.config import PipelineConfig, load_config


def test_load_config_validates_nested_values(tmp_path: Path) -> None:
    config_path = tmp_path / "pipeline.yaml"
    config_path.write_text(
        """
runtime:
  max_core_workers: 1
quality:
  fallback_threshold: 0.8
docling:
  enabled: false
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert isinstance(config, PipelineConfig)
    assert config.runtime.max_core_workers == 1
    assert config.quality.fallback_threshold == 0.8
    assert config.docling.enabled is False
