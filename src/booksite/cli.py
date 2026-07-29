from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Annotated

import pymupdf
import typer

from booksite.config import load_config
from booksite.pipeline import PipelineRunner

app = typer.Typer(
    no_args_is_help=True,
    help="Convert local text-layer PDF books into Docusaurus documentation sites.",
)


def _config_path(path: Path | None) -> Path | None:
    if path is not None:
        return path
    default = Path("pipeline.yaml")
    return default if default.exists() else None


def _runner(config: Path | None, workspace: Path) -> PipelineRunner:
    return PipelineRunner(load_config(_config_path(config)), workspace_root=workspace)


def _echo_result(label: str, path: Path) -> None:
    typer.echo(f"{label}: {path}")


@app.command()
def doctor(
    output: Annotated[Path, typer.Option(help="Generated site directory.")] = Path("site"),
) -> None:
    """Check the local core, optional engines, Node runtime, and output path."""
    checks = [
        ("OS", f"{platform.system()} {platform.machine()}"),
        ("Python", platform.python_version()),
        ("PyMuPDF", pymupdf.__version__),
        ("Docling", "installed" if importlib.util.find_spec("docling") else "optional / missing"),
        ("MinerU", shutil.which("mineru") or "optional / missing"),
        ("OvisOCR2", shutil.which("ovisocr2-parse") or "optional / missing"),
        ("Node", shutil.which("node") or "missing"),
        ("pnpm", os.environ.get("BOOKSITE_PNPM") or shutil.which("pnpm") or "missing"),
        ("Output", str(output.resolve())),
    ]
    for name, value in checks:
        typer.echo(f"{name:10} {value}")


@app.command()
def audit(
    pdf: Path,
    config: Annotated[Path | None, typer.Option()] = None,
    workspace: Annotated[Path, typer.Option()] = Path("workspace"),
    max_pages: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """Audit native PDF metadata and text without running layout models."""
    report, path, used_cache = _runner(config, workspace).audit(pdf, max_pages)
    typer.echo(f"Pages: {report.page_count}/{report.total_page_count}")
    typer.echo(f"Cache: {'hit' if used_cache else 'miss'}")
    _echo_result("Audit", path)


@app.command()
def parse(
    pdf: Path,
    config: Annotated[Path | None, typer.Option()] = None,
    workspace: Annotated[Path, typer.Option()] = Path("workspace"),
    max_pages: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """Parse the PDF into validated BookIR using cached audit data."""
    runner = _runner(config, workspace)
    report, _, _ = runner.audit(pdf, max_pages)
    book, used_cache = runner.assemble(pdf, report, max_pages)
    typer.echo(f"Pages parsed: {len(book.pages)}")
    typer.echo(f"Cache: {'hit' if used_cache else 'miss'}")


@app.command()
def repair(
    config: Annotated[Path | None, typer.Option()] = None,
) -> None:
    """Report which isolated fallback engines are enabled and configured."""
    settings = load_config(_config_path(config))
    typer.echo(f"MinerU enabled: {settings.mineru.enabled}")
    typer.echo(f"OvisOCR2 enabled: {settings.ovisocr2.enabled}")
    typer.echo("Fallback execution is page-routed; whole-book OCR is never automatic.")


@app.command()
def assemble(
    pdf: Path,
    config: Annotated[Path | None, typer.Option()] = None,
    workspace: Annotated[Path, typer.Option()] = Path("workspace"),
    max_pages: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """Resolve bookmarks and native blocks into chapter Markdown."""
    parse(pdf, config, workspace, max_pages)


def _run_pipeline(
    pdf: Path,
    config: Path | None,
    workspace: Path,
    output: Path,
    max_pages: int | None,
    force_page: int | None,
    build: bool,
) -> None:
    try:
        result = _runner(config, workspace).run_all(
            pdf,
            site_dir=output,
            max_pages=max_pages,
            force_page=force_page,
            build_site=build,
        )
    except (RuntimeError, ValueError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    _echo_result("Site", result.site_dir)
    _echo_result("BookIR", result.book_ir_path)
    _echo_result("Quality report", result.quality_report_path)
    if result.build_log_path:
        _echo_result("Build log", result.build_log_path)


@app.command("generate-site")
def generate_site(
    pdf: Path,
    config: Annotated[Path | None, typer.Option()] = None,
    workspace: Annotated[Path, typer.Option()] = Path("workspace"),
    output: Annotated[Path, typer.Option()] = Path("site"),
    max_pages: Annotated[int | None, typer.Option(min=1)] = None,
    force_page: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """Generate the Docusaurus files without running the production build."""
    _run_pipeline(pdf, config, workspace, output, max_pages, force_page, build=False)


@app.command()
def validate(
    pdf: Path,
    config: Annotated[Path | None, typer.Option()] = None,
    workspace: Annotated[Path, typer.Option()] = Path("workspace"),
    output: Annotated[Path, typer.Option()] = Path("site"),
    max_pages: Annotated[int | None, typer.Option(min=1)] = None,
) -> None:
    """Regenerate content and run the Docusaurus production build."""
    _run_pipeline(pdf, config, workspace, output, max_pages, None, build=True)


@app.command("all")
def all_stages(
    pdf: Path,
    config: Annotated[Path | None, typer.Option()] = None,
    workspace: Annotated[Path, typer.Option()] = Path("workspace"),
    output: Annotated[Path, typer.Option()] = Path("site"),
    max_pages: Annotated[int | None, typer.Option(min=1)] = None,
    force_page: Annotated[int | None, typer.Option(min=1)] = None,
    no_build: Annotated[
        bool,
        typer.Option(help="Skip the Docusaurus production build."),
    ] = False,
) -> None:
    """Run audit, parse, assemble, site generation, reporting, and validation."""
    _run_pipeline(
        pdf,
        config,
        workspace,
        output,
        max_pages,
        force_page,
        build=not no_build,
    )


if __name__ == "__main__":
    sys.exit(app())
