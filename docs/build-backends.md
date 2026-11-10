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

`--draft` (YAML `build_draft: true`) compiles the document with graphicx's `draft`
option: every figure is replaced by a box of the same size with the file name
in it. The layout, page numbers and references are those of the full build,
and the compilation is faster for figure-heavy documents because the figures
are not embedded in the PDF.

The draft is compiled as a separate LaTeX job named `<stem>-draft`
(`doc-draft.aux`, `doc-draft.log`, `doc-draft.pdf`), so draft and full builds
keep their own auxiliary files and latexmk can skip either one when nothing
changed since its last run. The PDF is still written to the `--output` path
(by default `<build>/<stem>.pdf`). Without the
[precompiled preamble](#precompiled-preamble), with latexmk the job is run as

```bash
latexmk -pdf -jobname=doc-draft -usepretex='\PassOptionsToPackage{draft}{graphicx}' doc.tex
```

and with the `raw` backend the option is put in the engine's input argument
(`pdflatex -jobname=doc-draft '\PassOptionsToPackage{draft}{graphicx}\input{doc.tex}'`).
With the precompiled preamble, graphicx is already loaded when the run
starts, so the option is set by a line of the `.tex` that runs after the
preamble when the job name is `<stem>-draft`.

Limitations:

- The `tectonic` backend has no draft mode; texmark warns and builds with
  figures.
- Projects with [companion documents](multi-file.md) build with figures
  (with a warning): cross-document references are read from each document's
  `<stem>.aux`, which a draft job does not update.

## Progressive builds

```bash
texmark doc.md --pdf --progressive
```

`--progressive` (YAML `build_progressive: true`) writes the PDF in three stages and
replaces the output PDF after each one, so a viewer that reloads on change
shows a first version early:

1. One engine pass of the draft job. The `.aux` and `.bbl` of the previous
   draft build are reused, so the existing references and citations are
   right; only labels and citations added since then show as `??`. Printed
   as `draft PDF (1 pass) written: <output>`.
2. The backend to completion on the draft job: bibtex/biber and further
   passes where needed. The PDF is published again only if it changed.
   Printed as `draft PDF (references resolved) written: <output>`.
3. The full build with figures (`PDF with figures written: <output>`).
   Skipped when `--draft` is also given.

Each line also gives the time since the build started. On a LaTeX error in
stage 1 texmark prints the error lines and continues with stage 2, as the
full build continues past errors. The first draft build in a build directory
that already has a full build starts from the full job's `.aux`, `.bbl` and
`.toc`, so stage 1 already shows the existing references.

This is the recommended loop while writing, combined with `--watch` (see
[Live preview](live-preview.md)):

```bash
texmark doc.md --pdf --progressive --watch
```

The stages run one after the other, so the PDF with figures comes later than
with a plain build. Use `--progressive --draft` to stop after stage 2.

With [companion documents](multi-file.md), stages 1 and 2 compile the root
document only; stage 3 compiles every document as a plain build does. With
the `tectonic` backend, `--progressive` is ignored with a warning.

## Precompiled preamble

With pdflatex and the `latexmk` or `raw` backend, texmark dumps the preamble
(document class, packages, title block, `preamble:` content) into a format
file, `<build>/<stem>-preamble.fmt`, with the `mylatexformat` package of TeX
Live, and starts every LaTeX pass from it:

```bash
pdflatex -ini -jobname=doc-preamble "&pdflatex" mylatexformat.ltx doc.tex   # once
latexmk -pdf -pdflatex="pdflatex -fmt=doc-preamble %O %S" doc.tex
```

Each pass then skips loading the packages. On a thesis with classicthesis
this saves about 1.5 s per pass; the PDF is the same.

The templates mark the end of the precompiled part with the line
`\csname endofdump\endcsname`, which does nothing when the document is
compiled without the format. What comes after it is read on every pass:
`\externaldocument` (companion labels), `\includeonly` (`--only`) and the
draft switch.

The format is rebuilt when the preamble text, the pdflatex version, the base
`pdflatex.fmt`, or one of the files read while building it (local `.sty`
files, files `\input` by the preamble, installed packages) changes; this is
recorded in `<build>/<stem>-preamble.json`. Building it takes about as long
as one LaTeX pass.

texmark compiles the usual way, with one message, when `mylatexformat.ltx`
is not installed, when building the format fails, or when a run with the
format fails because of it; the last two are remembered until the preamble
changes. The engines `xelatex` and `lualatex`, the `tectonic` backend and
custom templates without the marker line never use a format.

To disable it: `--no-preamble-format`, or in the YAML:

```yaml
build_preamble_format: false
```

> **Unicode and HTML in bibliographies / body text** — texmark transparently
> rewrites non-ASCII Unicode and CrossRef-style HTML markup
> (`<i>δ</i><sup>18</sup>O`) into LaTeX commands at build time, so pdflatex
> doesn't silently drop scientific characters from your references. Default
> behaviour is engine-aware (`--rewrite-unicode auto`): on for pdflatex,
> off for lualatex/xelatex; pass `on`/`off` to override. See
> [the encoding strategy page](encoding.md) for the full strategy, performance
> numbers, and how the engine choice affects it.
