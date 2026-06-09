<!--
  Home page. The feature bullets are pulled straight from README.md (single
  source of truth) via the include-markdown plugin; everything else links into
  the guide.
-->
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/perrette/texmark/main/icons/texmark-D-stacked-dark.svg">
    <img src="https://raw.githubusercontent.com/perrette/texmark/main/icons/texmark-D-stacked.svg" alt="texmark" width="180">
  </picture>
</p>

# texmark

Write scientific articles in markdown — and submit them to any journal.

{%
  include-markdown "../README.md"
  start="<!-- intro-start -->"
  end="<!-- intro-end -->"
%}

## Get started

```bash
pip install texmark
texmark example.md --pdf
```

- **[Installation](installation.md)** — pandoc, LaTeX, and the per-platform details.
- **[Quickstart](quickstart.md)** — your first markdown → PDF build.
- **[Journal templates](journals/index.md)** — Copernicus, Science, AMS, AGU, Nature, Elsevier, PNAS, arXiv, …
- **[YAML reference](yaml-reference.md)** — every front-matter field in one place.

## Guides

- [Numbered equations](equations.md)
- [Multi-file projects](multi-file.md) — chapters, supplementary information, cross-references.
- [Custom preamble](preamble.md)
- [Encoding (Unicode & HTML)](encoding.md)
- [Figure paths](figures.md)
- [Build backends and engines](build-backends.md)
- [Live preview](live-preview.md)
- [Custom LaTeX templates](custom-templates.md)
