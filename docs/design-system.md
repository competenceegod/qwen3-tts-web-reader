# Book reader design system

Source of truth: `design/book-reader-concept.png`.

## Visible-copy lock

The generated site chrome may show:

- `Booksite`
- the extracted book title
- `Read`
- `Quality report`
- `Search this book`
- `Contents`
- `On this page`
- document titles and extracted source-page ranges

No marketing eyebrow, badge, metric, or promotional copy is permitted.

## Layout

- True white background.
- Quiet 64px top navigation.
- Left docs rail: 270-300px.
- Main article: 850-950px maximum width.
- Right on-page TOC: 200-240px.
- Sticky desktop rails; Docusaurus mobile drawers at narrow widths.
- Open reading canvas with borders only where they clarify structure.

## Tokens

```css
--booksite-accent: #1463ff;
--booksite-ink: #121826;
--booksite-muted: #5f6b7a;
--booksite-border: #dfe4ea;
--booksite-surface: #f6f8fb;
--booksite-code: #111827;
--booksite-radius: 6px;
--booksite-body-leading: 1.72;
```

## Typography and components

- UI: clean system grotesk at 13-16px.
- Article body: highly readable serif stack at 17-19px.
- Headings: editorial serif with strong weight and compact line height.
- Code: native monospace, 14px, horizontal overflow enabled.
- Tables: horizontal overflow and sticky header rows.
- Images: max-width 100%, centered, with restrained captions.
- Source-page marker: muted utility text below each generated section.

## Responsive behavior

- Hide the right TOC below Docusaurus's standard desktop breakpoint.
- Use the built-in mobile sidebar drawer.
- Keep all content, code, math, and tables inside the viewport.
- Preserve at least 20px side padding on small screens.

