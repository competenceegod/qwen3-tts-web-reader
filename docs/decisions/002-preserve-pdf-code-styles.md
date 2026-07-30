# ADR-002: Preserve PDF code styles as structured BookIR data

## Status

Accepted

## Date

2026-07-30

## Context

Fenced Markdown preserves code text but delegates color, typography, spacing,
and background treatment to Docusaurus Prism themes. That makes the web reader
visually inconsistent with the source PDF even when PyMuPDF already exposes
the original span colors, fonts, flags, sizes, and drawing surfaces.

The reader must retain source fidelity without embedding page screenshots,
because code still needs to be selectable, searchable, copyable, responsive,
and accessible.

## Decision

Store PDF code lines and spans as structured BookIR data. Each span records its
text, foreground color, declared font family, point size, bold state, and
italic state. Each code block also records the containing PDF drawing's
background fill and accent-rule color when available.

During section assembly, adjacent PDF code blocks are merged in source order,
including geometry-derived blank lines, and serialized as a `PdfCodeBlock` MDX
component. The generated Docusaurus site supplies that component globally. It
renders semantic `pre`/`code` markup, literal PDF colors, local font fallbacks,
horizontal scrolling, and a copy button.

The component uses only local CSS and JavaScript. It does not fetch a web font
or run a syntax highlighter that could override source colors.

## Alternatives considered

### Continue using fenced Markdown and Prism

- Pros: Minimal implementation; Docusaurus supplies highlighting and copying.
- Cons: Colors and typography reflect the selected website theme, not the PDF.
- Rejected: Cannot meet source-style fidelity.

### Render each code block as a bitmap

- Pros: Pixel-level visual similarity.
- Cons: Text is not selectable, searchable, reflowable, or accessible; images
  become blurry when zoomed.
- Rejected: Conflicts with the semantic-reader objective.

### Re-run a language syntax highlighter with a matching theme

- Pros: Compact data and familiar highlighting.
- Cons: Language detection can be wrong, colors still approximate the source,
  and non-code terminal/config blocks are easily misclassified.
- Rejected: The PDF already contains authoritative span styling.

## Consequences

- BookIR gains explicit code-style models and its cache schema version changes.
- Generated Markdown becomes MDX for styled code blocks.
- Generated sites include one small React component and CSS rules.
- Fonts are matched by family name only; when the PDF font is not installed,
  a local monospace fallback is used.
- Code layout remains responsive rather than reproducing fixed PDF page width.
