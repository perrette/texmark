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

Write scientific articles in Markdown and convert them to journal-ready LaTeX and PDF.

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

## From the same author

A few related tools I maintain, useful in a Markdown-based scientific workflow.

**Scientific writing & data**

- [**texmark**](https://perrette.github.io/texmark/) — write scientific articles in Markdown and convert them to journal-ready LaTeX/PDF.
- [**papers**](https://perrette.github.io/papers/) — command-line BibTeX bibliography and PDF library manager.
- [**datamanifest**](https://perrette.github.io/datamanifest/) — declarative, reproducible dataset management. *(See also the [datamanifest.toml](https://perrette.github.io/datamanifest.toml/) format spec and the [DataManifest.jl](https://awi-esc.github.io/DataManifest.jl/) Julia port.)*

**Voice helpers** — handy for dictating and proofreading drafts by ear

- [**scribe**](https://perrette.github.io/scribe/) — speech-to-text dictation (Whisper).
- [**bard**](https://perrette.github.io/bard/) — text-to-speech reader (Kokoro / Piper).
