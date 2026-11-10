# Build backends and engines

texmark separates the **driver** (what orchestrates LaTeX passes and bibtex)
from the **engine** (the actual TeX program). Both have sensible defaults and
both are configurable from the CLI or YAML.

| `--backend` | What it does | Honors `--engine`? |
| --- | --- | --- |
| `latexmk` *(default)* | Reads `.aux`/`.fls`/`.bbl` between passes and reruns *only* what's stale. Drives bibtex automatically. Typically **2–3× faster** on incremental edits than the old fixed 3-pass sequence. | yes |
| `raw` | Runs `engine → bibtex → engine → engine` unconditionally — the original behaviour. Use when latexmk isn't available. | yes |
| `tectonic` | Standalone Rust rewrite of the TeX stack: engine + driver + bibtex-equivalent in one binary. Auto-fetches missing packages on first run. | no — uses its own XeTeX-derived engine |

`--engine` selects the TeX program when the backend honors it:

- `pdflatex` *(default)* — broadest package compatibility, fastest cold start.
- `xelatex` — native Unicode + system OpenType fonts (`fontspec`).
- `lualatex` — LuaTeX scripting + modern fontspec.

YAML frontmatter equivalents:

```yaml
backend: latexmk          # or raw, tectonic
engine: pdflatex          # or xelatex, lualatex
```

CLI flags win over YAML.

## Draft builds

```bash
texmark doc.md --pdf --draft
```

`--draft` (YAML `draft: true`) compiles the document with graphicx's `draft`
option: every figure is replaced by a box of the same size with the file name
in it. The layout, page numbers and references are those of the full build,
and the compilation is faster for figure-heavy documents because the figures
are not embedded in the PDF.

The draft is compiled as a separate LaTeX job named `<stem>-draft`
(`doc-draft.aux`, `doc-draft.log`, `doc-draft.pdf`), so draft and full builds
keep their own auxiliary files and latexmk can skip either one when nothing
changed since its last run. The PDF is still written to the `--output` path
(by default `<build>/<stem>.pdf`). With latexmk the job is run as

```bash
latexmk -pdf -jobname=doc-draft -usepretex='\PassOptionsToPackage{draft}{graphicx}' doc.tex
```

and with the `raw` backend the option is put in the engine's input argument
(`pdflatex -jobname=doc-draft '\PassOptionsToPackage{draft}{graphicx}\input{doc.tex}'`).

Limitations:

- The `tectonic` backend has no draft mode; texmark warns and builds with
  figures.
- Projects with [companion documents](multi-file.md) build with figures
  (with a warning): cross-document references are read from each document's
  `<stem>.aux`, which a draft job does not update.

> **Unicode and HTML in bibliographies / body text** — texmark transparently
> rewrites non-ASCII Unicode and CrossRef-style HTML markup
> (`<i>δ</i><sup>18</sup>O`) into LaTeX commands at build time, so pdflatex
> doesn't silently drop scientific characters from your references. Default
> behaviour is engine-aware (`--rewrite-unicode auto`): on for pdflatex,
> off for lualatex/xelatex; pass `on`/`off` to override. See
> [the encoding strategy page](encoding.md) for the full strategy, performance
> numbers, and how the engine choice affects it.
