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

Write scientific articles in markdown — and submit them to any journal.

<!-- intro-start -->
- **Instant preview.** Markdown renders live in most editors (VS Code, Cursor,
  JetBrains, vim) and on GitHub itself, so you see your draft as you type. No
  more wait-on-pdflatex cycles every time you change a sentence.
- **Git + GitHub as a paper backend.** Branches, pull requests, issues, blame,
  and diffs work the way they were designed to. Collaborators review changes
  with the same tooling they already use for code.
- **One source, any journal.** texmark compiles your markdown to any of the
  [supported LaTeX templates](https://perrette.github.io/texmark/journals/).
  Start writing first, decide on a target journal later, and switch mid-way
  (or after rejection) by flipping a single yaml field — no rewriting needed.
- **No lock-in.** The intermediate `.tex` is right there next to the PDF.
  Unplug texmark whenever you want and continue the manuscript in plain
  LaTeX — useful for the final polish that journals usually demand.
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

## Acknowledgements

This project benefited greatly from AI support to extend the initial list of
supported journals and further extend this package capability.
