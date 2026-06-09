<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/perrette/texmark/main/icons/texmark-D-stacked-dark.svg">
    <img src="https://raw.githubusercontent.com/perrette/texmark/main/icons/texmark-D-stacked.svg" alt="texmark" width="180">
  </picture>
</p>

# texmark

[![pypi](https://img.shields.io/pypi/v/texmark)](https://pypi.org/project/texmark)
![python](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fperrette%2Ftexmark%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)
[![tests](https://github.com/perrette/texmark/actions/workflows/tests.yml/badge.svg)](https://github.com/perrette/texmark/actions/workflows/tests.yml)
[![docs](https://img.shields.io/badge/docs-perrette.github.io%2Ftexmark-blue)](https://perrette.github.io/texmark/)

Write scientific articles in Markdown and convert them to journal-ready LaTeX and PDF.

<!-- intro-start -->
- **Preview while writing.** Markdown renders in most editors (VS Code,
  JetBrains, vim) and on GitHub — equations included — so you can read a draft
  without running a LaTeX build.
- **Lightweight, portable text.** Markdown uses much less markup than LaTeX, so
  the source stays readable and works with ordinary tools: edit it on GitHub,
  version it with Git (branches, diffs, pull requests), or paste it into a
  Google Doc to draft interactively with collaborators who prefer that, then
  bring it back.
- **One source, several journal templates.** The same Markdown compiles to any
  of the [supported LaTeX templates](https://perrette.github.io/texmark/journals/);
  changing the target journal means editing one field in the YAML header rather
  than reformatting the text.
- **LaTeX output is kept.** The generated `.tex` sits next to the PDF, so you
  can stop using texmark at any point and continue in LaTeX directly — usually
  necessary for the final journal-specific adjustments anyway.
<!-- intro-end -->

## 📖 Documentation

Full documentation lives at **<https://perrette.github.io/texmark/>**:

- [Installation](https://perrette.github.io/texmark/installation/) (incl. external dependencies)
- [Quickstart](https://perrette.github.io/texmark/quickstart/)
- [Journal templates](https://perrette.github.io/texmark/journals/)
- [YAML reference](https://perrette.github.io/texmark/yaml-reference/)
- Guides: [equations](https://perrette.github.io/texmark/equations/),
  [multi-file projects](https://perrette.github.io/texmark/multi-file/),
  [custom preamble](https://perrette.github.io/texmark/preamble/),
  [encoding](https://perrette.github.io/texmark/encoding/),
  [figures](https://perrette.github.io/texmark/figures/),
  [build backends](https://perrette.github.io/texmark/build-backends/),
  [live preview](https://perrette.github.io/texmark/live-preview/),
  [custom LaTeX templates](https://perrette.github.io/texmark/custom-templates/)

## Installation

```bash
pip install texmark
```

texmark also needs **pandoc** and a **LaTeX distribution** (`pdflatex`,
`bibtex`, `latexmk`). See the
[installation page](https://perrette.github.io/texmark/installation/) for the
per-platform details.

## Quickstart

See [example.md](example.md) for a sample markdown file with yaml metadata in
the header.

```bash
texmark example.md          # markdown → tex
texmark example.md --pdf    # markdown → pdf
```

For another journal, change the `journal -> template` field in the yaml
metadata, or pass `-j` for a quick test:

```bash
texmark example.md --pdf -j science -o build/example-science.pdf --tex build/example-science.tex
```

See the [quickstart](https://perrette.github.io/texmark/quickstart/) and
[journal templates](https://perrette.github.io/texmark/journals/) pages for more.

## From the same author

A few related tools I maintain, useful in a Markdown-based scientific workflow.

**Scientific writing & data**

- [**texmark**](https://perrette.github.io/texmark/) — write scientific articles in Markdown and submit them to any journal (Markdown → LaTeX/PDF).
- [**papers**](https://perrette.github.io/papers/) — command-line BibTeX bibliography and PDF library manager.
- [**datamanifest**](https://perrette.github.io/datamanifest/) — declarative, reproducible dataset management. *(See also the [datamanifest.toml](https://perrette.github.io/datamanifest.toml/) format spec and the [DataManifest.jl](https://awi-esc.github.io/DataManifest.jl/) Julia port.)*

**Voice helpers** — handy for dictating and proofreading drafts by ear

- [**scribe**](https://perrette.github.io/scribe/) — speech-to-text dictation (Whisper).
- [**bard**](https://perrette.github.io/bard/) — text-to-speech reader (Kokoro / Piper).

## Acknowledgements

Parts of this project — notably extending the set of supported journals — were
developed with AI assistance.
