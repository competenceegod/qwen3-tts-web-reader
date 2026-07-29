from __future__ import annotations

import csv
import html
import io
import json
from dataclasses import dataclass
from pathlib import Path

from booksite.models.book_ir import BookIR
from booksite.utils.cache import atomic_write_text


@dataclass(frozen=True, slots=True)
class ReportPaths:
    summary: Path
    html: Path
    page_quality: Path
    warnings: Path


def _summary(book: BookIR) -> dict[str, object]:
    review_pages = [page for page in book.pages if page.fallback_reasons]
    return {
        "book_id": book.book_id,
        "title": book.title,
        "page_count": book.page_count,
        "section_count": len(book.sections),
        "asset_count": len(book.assets),
        "warning_count": len(book.warnings),
        "native_pages": book.page_count,
        "fallback_pages": 0,
        "manual_review_pages": len(review_pages),
        "average_quality_score": round(
            sum(page.quality_score for page in book.pages) / max(len(book.pages), 1),
            4,
        ),
    }


def _page_quality_csv(book: BookIR) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["page", "selected_engine", "quality_score", "native_chars", "fallback_reasons"]
    )
    for page in book.pages:
        writer.writerow(
            [
                page.page_index + 1,
                page.selected_engine,
                page.quality_score,
                page.native_text_char_count,
                ";".join(page.fallback_reasons),
            ]
        )
    return output.getvalue()


def _html_report(book: BookIR, summary: dict[str, object]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{page.page_index + 1}</td>"
        f"<td>{html.escape(page.selected_engine)}</td>"
        f"<td>{page.quality_score:.2f}</td>"
        f"<td>{page.native_text_char_count}</td>"
        f"<td>{html.escape(', '.join(page.fallback_reasons) or '—')}</td>"
        "</tr>"
        for page in book.pages
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Quality report — {html.escape(book.title or "Converted book")}</title>
  <style>
    body {{ font: 15px/1.55 Inter, system-ui, sans-serif; color: #121826;
      max-width: 1100px; margin: 0 auto; padding: 48px 24px; }}
    a {{ color: #1463ff; }} h1 {{ font: 700 42px/1.1 Georgia, serif; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 1px; background: #dfe4ea; border: 1px solid #dfe4ea; }}
    .metric {{ background: white; padding: 20px; }}
    .metric strong {{ display: block; font-size: 24px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 32px; }}
    th, td {{ text-align: left; border-bottom: 1px solid #dfe4ea; padding: 10px; }}
    th {{ position: sticky; top: 0; background: #f6f8fb; }}
  </style>
</head>
<body>
  <p><a href="/">← Back to book</a></p>
  <h1>Quality report</h1>
  <p>{html.escape(book.title or "Converted book")} · local native-text pipeline</p>
  <section class="summary">
    <div class="metric"><strong>{summary["page_count"]}</strong>pages</div>
    <div class="metric"><strong>{summary["section_count"]}</strong>sections</div>
    <div class="metric"><strong>{summary["asset_count"]}</strong>assets</div>
    <div class="metric"><strong>{summary["manual_review_pages"]}</strong>review pages</div>
    <div class="metric"><strong>{summary["average_quality_score"]}</strong>avg quality</div>
  </section>
  <table>
    <thead><tr><th>Page</th><th>Engine</th><th>Score</th><th>Chars</th>
      <th>Review reason</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""


def write_quality_report(book: BookIR, report_dir: str | Path) -> ReportPaths:
    target = Path(report_dir)
    target.mkdir(parents=True, exist_ok=True)
    summary = _summary(book)
    summary_path = target / "summary.json"
    html_path = target / "summary.html"
    page_quality_path = target / "page-quality.csv"
    warnings_path = target / "warnings.jsonl"
    atomic_write_text(
        summary_path,
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    )
    atomic_write_text(html_path, _html_report(book, summary))
    atomic_write_text(page_quality_path, _page_quality_csv(book))
    atomic_write_text(
        warnings_path,
        "".join(
            json.dumps(warning.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for warning in book.warnings
        ),
    )
    return ReportPaths(summary_path, html_path, page_quality_path, warnings_path)
