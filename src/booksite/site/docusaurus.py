from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from booksite.models.book_ir import BookIR


@dataclass(frozen=True, slots=True)
class SiteGenerationResult:
    site_dir: Path
    docs_dir: Path
    document_paths: tuple[Path, ...]


def _js_string(value: str | None) -> str:
    return json.dumps(value or "Converted Book", ensure_ascii=True)


def _plain_search_text(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"[#>*_`|~-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _search_index_json(book: BookIR) -> str:
    entries = [
        {
            "title": section.title,
            "url": "/" if index == 0 else f"/{section.slug}",
            "pages": section.source_pages,
            "text": _plain_search_text(section.markdown),
        }
        for index, section in enumerate(book.sections)
    ]
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n"


def _frontmatter(book: BookIR, index: int) -> str:
    section = book.sections[index]
    previous_id = book.sections[index - 1].section_id if index > 0 else None
    next_id = book.sections[index + 1].section_id if index + 1 < len(book.sections) else None
    lines = [
        "---",
        f"id: {section.section_id}",
        f"title: {json.dumps(section.title, ensure_ascii=False)}",
        f"sidebar_position: {section.order}",
        f"slug: {'/' if index == 0 else '/' + section.slug}",
        "toc_min_heading_level: 2",
        "toc_max_heading_level: 5",
    ]
    if previous_id:
        lines.append(f"pagination_prev: {previous_id}")
    if next_id:
        lines.append(f"pagination_next: {next_id}")
    return "\n".join([*lines, "---", ""])


def _package_json() -> str:
    package = {
        "name": "generated-booksite",
        "version": "0.1.0",
        "private": True,
        "scripts": {
            "start": "docusaurus start",
            "build": "docusaurus build",
            "serve": "docusaurus serve",
            "clear": "docusaurus clear",
        },
        "dependencies": {
            "@docusaurus/core": "3.10.2",
            "@docusaurus/preset-classic": "3.10.2",
            "@mdx-js/react": "^3.0.0",
            "clsx": "^2.0.0",
            "katex": "0.16.22",
            "prism-react-renderer": "^2.3.0",
            "react": "^19.0.0",
            "react-dom": "^19.0.0",
            "rehype-katex": "7.0.1",
            "remark-math": "6.0.0",
        },
        "devDependencies": {
            "@docusaurus/module-type-aliases": "3.10.2",
            "@docusaurus/types": "3.10.2",
        },
        "engines": {"node": ">=20.0"},
    }
    return json.dumps(package, ensure_ascii=False, indent=2) + "\n"


def _preview_server_py() -> str:
    return '''#!/usr/bin/env python3
"""Serve the generated Docusaurus build over loopback HTTP."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import webbrowser


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview the generated book site.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--no-open", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_dir = Path(__file__).resolve().parent / "build"
    if not (build_dir / "index.html").is_file():
        raise SystemExit(
            "未找到 build/index.html。请先运行 PDF 转换，或执行 pnpm --dir site build。"
        )

    handler = partial(SimpleHTTPRequestHandler, directory=str(build_dir))
    try:
        server = ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as error:
        raise SystemExit(
            f"无法启动本地网站：{error}。可尝试 python3 serve-local.py --port 8001"
        ) from error

    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{display_host}:{server.server_port}/"
    print(f"本地网站：{url}", flush=True)
    print("保持此窗口开启；按 Control-C 停止。", flush=True)
    if not args.no_open:
        opener = threading.Timer(0.2, webbrowser.open, args=(url,))
        opener.daemon = True
        opener.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\n本地网站已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
'''


def _preview_launcher_sh() -> str:
    return """#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/env python3 "$SCRIPT_DIR/serve-local.py"
"""


def _preview_guide_text() -> str:
    return """本地打开生成的网站
====================

不要直接双击 build/index.html。Docusaurus 的静态资源和页面路由需要通过
HTTP 访问；file:// 协议会导致 CSS、JavaScript 和章节链接加载失败。

macOS：
1. 双击“打开网站.command”。
2. 默认浏览器会自动打开本地网站。
3. 阅读期间保持终端窗口开启；按 Control-C 停止。

命令行：
python3 serve-local.py

开发者也可以运行：
pnpm serve

部署时请上传 build/ 目录中的全部内容，不要把 baseUrl 改成本机文件路径。
"""


def _config_js(book: BookIR) -> str:
    title = _js_string(book.title)
    return f"""// Generated by booksite. Source patterns:
// https://docusaurus.io/docs/docs-introduction/
// https://docusaurus.io/docs/markdown-features/plugins
import {{themes as prismThemes}} from 'prism-react-renderer';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

/** @type {{import('@docusaurus/types').Config}} */
const config = {{
  title: {title},
  tagline: 'Local PDF book reader',
  url: 'http://localhost',
  baseUrl: '/',
  onBrokenLinks: 'throw',
  markdown: {{hooks: {{onBrokenMarkdownLinks: 'throw'}}}},
  i18n: {{defaultLocale: 'en', locales: ['en']}},
  presets: [[
    'classic',
    {{
      docs: {{
        routeBasePath: '/',
        sidebarPath: './sidebars.js',
        remarkPlugins: [remarkMath],
        rehypePlugins: [rehypeKatex],
      }},
      blog: false,
      theme: {{customCss: './src/css/custom.css'}},
    }},
  ]],
  themeConfig: {{
    colorMode: {{respectPrefersColorScheme: true}},
    navbar: {{
      title: 'Booksite',
      items: [
        {{to: '/', label: {title}, position: 'left', className: 'booksite-book-title'}},
        {{type: 'docSidebar', sidebarId: 'bookSidebar', label: 'Read', position: 'left'}},
        {{to: '/quality-report', label: 'Quality report', position: 'left'}},
        {{
          to: '/search',
          label: 'Search this book',
          position: 'right',
          className: 'booksite-search-link',
        }},
      ],
    }},
    docs: {{sidebar: {{hideable: true, autoCollapseCategories: false}}}},
    prism: {{theme: prismThemes.github, darkTheme: prismThemes.dracula}},
  }},
}};

export default config;
"""


def _search_page_js() -> str:
    return """import React, {useEffect, useMemo, useState} from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';

export default function SearchPage() {
  const [entries, setEntries] = useState([]);
  const [query, setQuery] = useState('');
  const indexUrl = useBaseUrl('/search-index.json');

  useEffect(() => {
    fetch(indexUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`Search index: ${response.status}`);
        return response.json();
      })
      .then(setEntries)
      .catch(() => setEntries([]));
  }, [indexUrl]);

  const results = useMemo(() => {
    const terms = query.toLocaleLowerCase().trim().split(/\\s+/).filter(Boolean);
    if (!terms.length) return entries.slice(0, 12);
    return entries.filter((entry) => {
      const haystack = `${entry.title} ${entry.text}`.toLocaleLowerCase();
      return terms.every((term) => haystack.includes(term));
    }).slice(0, 40);
  }, [entries, query]);

  return (
    <Layout title="Search" description="Search this converted book locally">
      <main className="booksite-search-page">
        <p className="booksite-eyebrow">LOCAL BOOK INDEX</p>
        <h1>Search this book</h1>
        <label className="booksite-search-field">
          <span className="sr-only">Search terms</span>
          <input
            autoFocus
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search chapters and text…"
          />
        </label>
        <p className="booksite-search-count">
          {query ? `${results.length} matching sections` : 'Browse indexed sections'}
        </p>
        <ol className="booksite-search-results">
          {results.map((entry) => (
            <li key={entry.url}>
              <Link to={entry.url}><h2>{entry.title}</h2></Link>
              <p>{entry.text.slice(0, 240)}{entry.text.length > 240 ? '…' : ''}</p>
              <small>PDF pages {entry.pages[0]}–{entry.pages.at(-1)}</small>
            </li>
          ))}
        </ol>
      </main>
    </Layout>
  );
}
"""


def _quality_page_js(book: BookIR) -> str:
    pages = [
        {
            "page": page.page_index + 1,
            "engine": page.selected_engine,
            "score": page.quality_score,
            "chars": page.native_text_char_count,
            "reasons": page.fallback_reasons,
        }
        for page in book.pages
    ]
    average_quality = (
        sum(page.quality_score for page in book.pages) / len(book.pages) if book.pages else 0
    )
    report = {
        "title": book.title or "Converted book",
        "metrics": [
            {"label": "pages", "value": book.page_count},
            {"label": "sections", "value": len(book.sections)},
            {"label": "assets", "value": len(book.assets)},
            {
                "label": "review pages",
                "value": sum(bool(page.fallback_reasons) for page in book.pages),
            },
            {"label": "avg quality", "value": round(average_quality, 4)},
        ],
        "pages": pages,
    }
    payload = json.dumps(report, ensure_ascii=True, separators=(",", ":"))
    return f"""import React from 'react';
import Layout from '@theme/Layout';

const report = {payload};

export default function QualityReportPage() {{
  return (
    <Layout title="Quality report" description="Local PDF conversion quality report">
      <main className="booksite-report-page">
        <p className="booksite-eyebrow">CONVERSION AUDIT</p>
        <h1>Quality report</h1>
        <p className="booksite-report-subtitle">
          {{report.title}} · local native-text pipeline
        </p>
        <section className="booksite-metrics">
          {{report.metrics.map((metric) => (
            <div key={{metric.label}}>
              <strong>{{metric.value}}</strong>
              <span>{{metric.label}}</span>
            </div>
          ))}}
        </section>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Page</th><th>Engine</th><th>Score</th>
                <th>Chars</th><th>Review reason</th>
              </tr>
            </thead>
            <tbody>
              {{report.pages.map((page) => (
                <tr key={{page.page}}>
                  <td>{{page.page}}</td>
                  <td>{{page.engine}}</td>
                  <td>{{page.score.toFixed(2)}}</td>
                  <td>{{page.chars}}</td>
                  <td>{{page.reasons.join(', ') || '—'}}</td>
                </tr>
              ))}}
            </tbody>
          </table>
        </div>
      </main>
    </Layout>
  );
}}
"""


def _custom_css() -> str:
    return """@import 'katex/dist/katex.min.css';

:root {
  --ifm-color-primary: #1463ff;
  --ifm-color-primary-dark: #0052ef;
  --ifm-color-primary-darker: #004de1;
  --ifm-color-primary-darkest: #003fb9;
  --ifm-color-primary-light: #3277ff;
  --ifm-color-primary-lighter: #4180ff;
  --ifm-color-primary-lightest: #6f9fff;
  --ifm-background-color: #ffffff;
  --ifm-font-family-base: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  --ifm-heading-font-family: Georgia, "Times New Roman", serif;
  --ifm-font-color-base: #121826;
  --ifm-line-height-base: 1.72;
  --doc-sidebar-width: 285px;
  --booksite-border: #dfe4ea;
  --booksite-muted: #5f6b7a;
  --booksite-surface: #f6f8fb;
}

.navbar {
  border-bottom: 1px solid var(--booksite-border);
  box-shadow: none;
}

.navbar__brand { color: #1463ff; font-weight: 760; }
.navbar__title { font-size: 1.25rem; }
.booksite-book-title {
  max-width: 22rem;
  margin-left: 0.4rem;
  padding-left: 1.25rem;
  border-left: 1px solid var(--booksite-border);
  overflow: hidden;
  color: var(--ifm-font-color-base);
  font-weight: 680;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.booksite-search-link {
  min-width: 10rem;
  border: 1px solid var(--booksite-border);
  border-radius: 6px;
  color: var(--booksite-muted);
}
.booksite-search-link::before { content: "⌕"; margin-right: 0.5rem; }
.theme-doc-sidebar-container { border-right-color: var(--booksite-border) !important; }
.menu__link { border-radius: 6px; line-height: 1.45; }
.menu__link--active { border-left: 3px solid #1463ff; background: #f1f5ff; }

.theme-doc-markdown {
  max-width: 900px;
  padding-left: 32px;
  border-left: 2px solid #d8e4ff;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 1.08rem;
}

.theme-doc-markdown h1 { font-size: clamp(2.2rem, 4vw, 3.4rem); letter-spacing: -0.035em; }
.theme-doc-markdown h2 { margin-top: 2.25rem; }
.theme-doc-markdown em:last-child {
  color: var(--booksite-muted);
  font-family: var(--ifm-font-family-base);
  font-size: 0.84rem;
}

pre, code, .table-wrapper { max-width: 100%; overflow-x: auto; }
pre { border: 1px solid var(--booksite-border); border-radius: 6px; box-shadow: none; }
table { display: table; width: 100%; }
table thead { position: sticky; top: var(--ifm-navbar-height); z-index: 1; }
table th { background: var(--booksite-surface); }
img { display: block; max-width: 100%; height: auto; margin-inline: auto; }
.table-of-contents { font-size: 0.82rem; }
.table-of-contents::before {
  content: "On this page";
  display: block;
  margin-bottom: 0.75rem;
  color: var(--ifm-font-color-base);
  font-size: 0.9rem;
  font-weight: 720;
}

.booksite-search-page {
  width: min(840px, calc(100% - 40px));
  margin: 0 auto;
  padding: 72px 0 96px;
}
.booksite-eyebrow {
  margin: 0 0 0.75rem;
  color: var(--ifm-color-primary);
  font-size: 0.75rem;
  font-weight: 750;
  letter-spacing: 0.12em;
}
.booksite-search-page h1 {
  margin-bottom: 1.75rem;
  font-family: var(--ifm-heading-font-family);
  font-size: clamp(2.5rem, 7vw, 4.5rem);
}
.booksite-search-field input {
  width: 100%;
  padding: 0.9rem 1rem;
  border: 1px solid var(--booksite-border);
  border-radius: 7px;
  background: var(--ifm-background-color);
  color: var(--ifm-font-color-base);
  font: inherit;
}
.booksite-search-field input:focus {
  border-color: var(--ifm-color-primary);
  box-shadow: 0 0 0 3px rgb(20 99 255 / 14%);
  outline: none;
}
.booksite-search-count { margin: 0.8rem 0 1.5rem; color: var(--booksite-muted); }
.booksite-search-results { padding: 0; list-style: none; }
.booksite-search-results li {
  padding: 1.3rem 0;
  border-top: 1px solid var(--booksite-border);
}
.booksite-search-results h2 { margin: 0 0 0.35rem; font-size: 1.3rem; }
.booksite-search-results p { margin: 0 0 0.35rem; color: var(--booksite-muted); }
.booksite-search-results small { color: var(--booksite-muted); }

.booksite-report-page {
  width: min(1080px, calc(100% - 40px));
  margin: 0 auto;
  padding: 72px 0 96px;
}
.booksite-report-page h1 {
  margin-bottom: 0.4rem;
  font-family: var(--ifm-heading-font-family);
  font-size: clamp(2.5rem, 7vw, 4.5rem);
}
.booksite-report-subtitle { color: var(--booksite-muted); }
.booksite-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  gap: 1px;
  margin: 2rem 0;
  border: 1px solid var(--booksite-border);
  background: var(--booksite-border);
}
.booksite-metrics div { padding: 1.25rem; background: var(--ifm-background-color); }
.booksite-metrics strong { display: block; font-size: 1.5rem; }
.booksite-metrics span { color: var(--booksite-muted); }

@media (max-width: 996px) {
  .theme-doc-markdown {
    padding-left: 0;
    border-left: 0;
    font-size: 1rem;
  }
  .main-wrapper main { padding-inline: 20px; }
  .booksite-search-link { min-width: auto; border: 0; }
  .booksite-book-title { max-width: none; border-left: 0; }
}
"""


def generate_docusaurus_site(book: BookIR, site_dir: str | Path) -> SiteGenerationResult:
    target = Path(site_dir)
    docs_dir = target / "docs"
    css_dir = target / "src" / "css"
    pages_dir = target / "src" / "pages"
    static_dir = target / "static"
    docs_dir.mkdir(parents=True, exist_ok=True)
    css_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    static_dir.mkdir(parents=True, exist_ok=True)

    for old_doc in docs_dir.glob("*.md"):
        old_doc.unlink()

    document_paths = []
    for index, section in enumerate(book.sections):
        safe_slug = re.sub(r"[^a-z0-9-]+", "-", section.slug.casefold()).strip("-")
        document_path = docs_dir / f"{section.order:02d}-{safe_slug}.md"
        document_path.write_text(
            _frontmatter(book, index) + "\n" + section.markdown,
            encoding="utf-8",
        )
        document_paths.append(document_path)

    (target / "package.json").write_text(_package_json(), encoding="utf-8")
    stale_config = target / "docusaurus.config.js"
    if stale_config.exists():
        stale_config.unlink()
    (target / "docusaurus.config.mjs").write_text(_config_js(book), encoding="utf-8")
    (target / "sidebars.js").write_text(
        "export default {bookSidebar: [{type: 'autogenerated', dirName: '.'}]};\n",
        encoding="utf-8",
    )
    (target / "pnpm-workspace.yaml").write_text(
        "autoInstallPeers: false\nallowBuilds:\n  '@swc/core': true\n  core-js: true\n",
        encoding="utf-8",
    )
    preview_server = target / "serve-local.py"
    preview_server.write_text(_preview_server_py(), encoding="utf-8")
    preview_launcher = target / "打开网站.command"
    preview_launcher.write_text(_preview_launcher_sh(), encoding="utf-8")
    preview_launcher.chmod(0o755)
    (target / "本地打开说明.txt").write_text(
        _preview_guide_text(),
        encoding="utf-8",
    )
    (pages_dir / "search.js").write_text(_search_page_js(), encoding="utf-8")
    (pages_dir / "quality-report.js").write_text(
        _quality_page_js(book),
        encoding="utf-8",
    )
    (static_dir / "search-index.json").write_text(
        _search_index_json(book),
        encoding="utf-8",
    )
    (css_dir / "custom.css").write_text(_custom_css(), encoding="utf-8")
    return SiteGenerationResult(target, docs_dir, tuple(document_paths))
