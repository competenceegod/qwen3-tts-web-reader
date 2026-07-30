# ADR-001: Isolate generated sites by PDF identity

## Status

Accepted

## Date

2026-07-30

## Context

The original CLI treated `--output site` as one Docusaurus application.
Converting a second PDF into the same path overwrote documents, configuration,
search data, assets, and build output from the first PDF. Users need to keep
multiple converted books locally without manually choosing a unique output
directory every time.

The directory name must be readable, safe for local filesystems and URLs, and
collision-resistant when two different PDF files share the same filename.

## Decision

Treat `--output` as a collection root. The pipeline writes each generated
Docusaurus application to:

```text
<output>/<book-id>/
```

`book-id` is the existing normalized PDF filename plus the first eight
characters of the source SHA-256 hash. `PipelineResult.site_dir` and CLI output
continue to report the concrete per-book Docusaurus directory.

Each book directory owns its dependencies, source documents, assets, search
index, quality report, production build, and local preview launcher.
Reprocessing a PDF updates only the directory with the same `book-id`; sibling
book directories are never scanned, cleaned, or modified.

The short hash makes the directory readable, but it is not the ownership
boundary. Every generated directory contains `.booksite-site.json` with the
full source SHA-256. A mismatched manifest, an unowned non-empty directory, or
a symbolic-link target is rejected before any generated files are changed.

Generation occurs in a sibling staging directory. Only after source generation,
content validation, and the optional production build all succeed is staging
promoted to the stable book directory. A failed rerun leaves the previous site
available. A legacy flat Docusaurus root is rejected with migration guidance
instead of being mixed with per-book directories.

## Alternatives considered

### Keep one flat output directory

- Pros: No interface change.
- Cons: Every conversion can destroy the previous book.
- Rejected: Directly conflicts with multi-book use.

### Use the exact PDF filename

- Pros: Most recognizable folder name.
- Cons: Unsafe punctuation and Unicode vary across filesystems; same-name PDFs
  collide.
- Rejected: Normalization and a content suffix are required for stability.

### Merge all PDFs into one Docusaurus application

- Pros: One global homepage and one server.
- Cons: Requires cross-book routing, navigation, search, asset, and lifecycle
  coordination; one failed build can affect every book.
- Rejected: Independent sites provide stronger isolation and simpler recovery.

## Consequences

- Existing commands still use `--output site`, but the concrete application
  moves one level deeper.
- Scripts that assumed `site/build` must use the `Site:` path printed by the
  CLI, such as `site/<book-id>/build`.
- Existing root-level generated sites require a one-time move or regeneration;
  the CLI detects and refuses that mixed layout.
- Rebuilds require temporary disk space for staging and, briefly, the prior
  version used for rollback.
- Static deployment remains per-book unless a future catalog feature is added.
