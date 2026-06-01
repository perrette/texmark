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

Write scientific articles in markdown — and submit them to any journal.

- **Instant preview.** Markdown renders live in most editors (VS Code, Cursor,
  JetBrains, vim) and on GitHub itself, so you see your draft as you type. No
  more wait-on-pdflatex cycles every time you change a sentence.
- **Git + GitHub as a paper backend.** Branches, pull requests, issues, blame,
  and diffs work the way they were designed to. Collaborators review changes
  with the same tooling they already use for code.
- **One source, any journal.** texmark compiles your markdown to any of the
  [supported LaTeX templates](#journal-templates). Start writing first, decide
  on a target journal later, and switch mid-way (or after rejection) by
  flipping a single yaml field — no rewriting needed.
- **No lock-in.** The intermediate `.tex` is right there next to the PDF.
  Unplug texmark whenever you want and continue the manuscript in plain
  LaTeX — useful for the final polish that journals usually demand.


## Installation

    pip install texmark


### External dependencies

texmark itself is pure Python, but it shells out to a few external tools to
produce the final PDF. Install them via your system package manager.

- **pandoc** — the markdown → tex engine (the `pypandoc` PyPI dependency is
  a wrapper, the binary is not installable via pip).
- **A LaTeX distribution** providing `pdflatex`, `bibtex`, and `latexmk`
  (texmark's default driver) plus the standard package set (`hyperref`,
  `natbib`, `amsmath`, `graphicx`, `geometry`, `microtype`, `booktabs`,
  `caption`, `mathptmx`, `newtxtext`, `newtxmath`, `apacite`,
  `draftwatermark`, `mdframed`, `tikz`, `xcolor`, `appendix`, `lineno`,
  `epstopdf`, …). Optionally `tectonic` as a single-binary alternative
  (see [Build backends](#build-backends-and-engines)).

On Debian / Ubuntu:

    sudo apt install pandoc \
        texlive-latex-extra texlive-bibtex-extra \
        texlive-publishers texlive-fonts-extra

…or just `texlive-full` for the easy answer.

On macOS (Homebrew):

    brew install pandoc
    brew install --cask mactex     # or basictex + tlmgr install <packages>

A handful of LaTeX packages that aren't in TeX Live's smaller installs
(notably `trackchanges`, `algorithm` / `algorithmicx`, `jabbrv`) are
**bundled with texmark** under `texmark/templates/<journal>/` and copied
into the build directory automatically, so you don't need to install them
separately.

## Example

See [example.md](example.md) for a sample markdown file with yaml metadata in the header.

The command to convert the markdow to tex is:

    texmark example.md

And to convert to PDF

    texmark example.md --pdf

For another journal, it is enough to change the `journal -> template' field in the yaml metadata.
For testing it is also possible to pass `-j` for `--journal-template`:

    texmark example.md --pdf -j science -o build/example-science.pdf --tex build/example-science.tex

See the example tex and pdf results in [build](/build)

## Build backends and engines

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

## Live preview (`--watch`)

```
texmark sources/main.md --pdf --watch
```

Rebuilds whenever the input markdown, bibliography, or template changes.
Combine with an auto-reloading PDF viewer (zathura, evince, okular) for a
live-preview workflow — the output PDF is rewritten in place so viewers
that follow inode changes keep your scroll position.

In multi-file projects `--watch` also tracks every embedded chapter and
every companion document (plus each companion's bibliography and template).

## Multi-file projects

Split a long manuscript across files by embedding chapters directly in
the markdown body:

```markdown
![](chapters/introduction.md)
![](chapters/methods.md)
![](chapters/results.md)
```

Or use the GitHub-clean link form (renders as a plain link on GitHub):

```markdown
[Introduction](chapters/introduction.md){.include}
```

Alternatively, declare the chapter set in YAML:

```yaml
chapters:
  - chapters/introduction.md
  - chapters/methods.md
  - chapters/results.md
```

texmark compiles each chapter to a body-only `.tex` and wires them
together with `\input{...}` (article-class templates) or `\include{...}`
(book-family templates). From LaTeX's perspective it is one document, so
all labels and cross-references work natively.

For book-family templates, `--only chapter.md` injects
`\includeonly{chapter}` for fast single-chapter iteration.

See [docs/multi-file.md](docs/multi-file.md) for the full reference.

## Main paper + supplementary information

Declare a companion document (separate PDF) in the root YAML:

```yaml
companions:
  - si.md
```

Reference a label in the companion using a `#anchor` markdown link:

```markdown
As shown in [Fig.~S1](si.md#fig:noise), the signal is clear.
```

texmark rewrites this to `\ref{si:fig:noise}` using xr-hyper's
`\externaldocument` machinery. Cross-references are validated at compile
time; a renamed label in the SI breaks the main paper's build, not just
the rendered output.

Give the companion independent figure numbering via its own YAML:

```yaml
# si.md
prefix: S
```

texmark loops the compile cycle (up to 4 passes) until all `.aux` files
stabilize, so xr-hyper cross-document references resolve correctly.

See [docs/multi-file.md](docs/multi-file.md) for the full reference,
including `prefix:`/per-counter overrides and watch-mode coverage.

## Custom preamble

Inject `\newcommand`, theorem environments, or package configuration
into the preamble without forking the template:

```yaml
preamble: |
  \newcommand{\degC}{^\circ\mathrm{C}}
  \DeclareMathOperator{\std}{std}
```

Also accepts a file path (`preamble: macros.tex`) or a list of paths.
Works across all templates. See [docs/preamble.md](docs/preamble.md).

## Journal templates

Pick the template that matches your target journal and add it to the yaml
header of your markdown:

```yaml
journal:
    template: ametsoc          # template name, see table below
    options: twocol            # optional, per-template — see the docs page
```

**Article-class templates** (single PDF, any journal):

| template | covers | example | docs |
| --- | --- | --- | --- |
| `copernicus` (aliases `cp`, `esd`, ...) | Copernicus / EGU: ACP, BG, CP, ESD, HESS, NHESS, TC, ... | [PDF](build/example.pdf) | [docs](docs/journals/copernicus.md) |
| `science` | AAAS Science, Science Advances | [PDF](build/example-science.pdf) | [docs](docs/journals/science.md) |
| `ametsoc` (aliases `jclim`, `jas`, `mwr`, `bams`, ...) | AMS: J. Climate, JAS, MWR, BAMS, ... | [PDF](build/example-ametsoc.pdf) | [docs](docs/journals/ametsoc.md) |
| `arxiv` (alias `preprint`) | arXiv preprint, generic article-class | [PDF](build/example-arxiv.pdf) | [docs](docs/journals/arxiv.md) |
| `elsarticle` (alias `elsevier`) | Elsevier: QSR, EPSL, GPC, Earth-Science Reviews, Cell, Lancet, ... | [PDF](build/example-elsarticle.pdf) | [docs](docs/journals/elsarticle.md) |
| `agujournal` (aliases `agu`, `jgr`, `grl`, `james`, `wrr`, ...) | AGU: JGR family, GRL, Earth's Future, JAMES, ... | [PDF](build/example-agujournal.pdf) | [docs](docs/journals/agujournal.md) |
| `springernature` (aliases `nature`, `naturecomms`, `natclimchange`, `natgeoscience`, `scirep`) | Springer Nature: Nature, Nature Communications, Nature Climate Change, Nature Geoscience, Scientific Reports, ... | [PDF](build/example-springernature.pdf) | [docs](docs/journals/springernature.md) |
| `pnas` | PNAS | [PDF](build/example-pnas.pdf) | [docs](docs/journals/pnas.md) |

**Book-family templates** (theses, monographs, multi-chapter documents):

| template | document class | structure | docs |
| --- | --- | --- | --- |
| `book` | `\documentclass{book}` | `\frontmatter` / `\mainmatter` / `\backmatter` | [docs](docs/journals/book.md) |
| `report` | `\documentclass{report}` | No front/main/back matter macros | [docs](docs/journals/report.md) |
| `memoir` | `\documentclass{memoir}` | `\frontmatter` / `\mainmatter` / `\backmatter`; configurable chapter styles | [docs](docs/journals/memoir.md) |
| `classicthesis` | `\documentclass{scrreprt}` + bundled `classicthesis.sty` | Bringhurst-inspired typography; no front/main/back matter macros | [docs](docs/journals/classicthesis.md) |

Book-family templates support `\include{...}` for chapters (enabling
`--only` for selective recompilation), front-matter YAML keys
(`dedication:`, `list_of_figures:`, etc.), and
`bibliography_per_chapter: true` for per-chapter biblatex bibliographies.

Each template ships a default `journal.options` value chosen to produce a
**publication-style** PDF (typeset 2-column journal look, no draft watermarks).
For peer-review submission you usually want to switch to the publisher's
submission options (e.g. `preprint,12pt` for Elsevier, `draft` for AGU, the
empty default for AMS 1.5-spacing). The per-journal docs page lists the
alternatives.

*Partial support only.* Before submitting, you will likely need to hand-edit
the final LaTeX — appendix structure, special sections (Methods Online,
Extended Data, Significance, …) and journal-specific cross-reference macros
are not all wired up automatically. Use the example PDF to confirm the
layout looks reasonable, then run `texmark --tex out.tex` and finish the
manuscript in LaTeX directly.

### Common yaml fields (all templates)

```yaml
title: "Paper title"
authors:
  - firstname: Mahé
    lastname: Perrette
    affiliation: 1              # integer index into `affiliations` (most templates)
    email: mahe.perrette@gmail.com
  - firstname: Co
    lastname: Author
    affiliation: 2
affiliations:
  - "Alfred Wegener Institute, ..."
  - "Another Institution"
date: "2026-05-26"
bibliography: references.bib
journal:
    template: <name>            # required: picks the journal template + filters
    options: <str or list>      # optional: class options (per-template default)
collect_figures_and_tables: true       # optional: see section below
figure-width: 80%                      # optional: pandoc figure default
figure-span: full                      # optional: wraps in figure* (full text width)
                                       #   per-figure override: ![cap](img){figure-span=full}
copy_figures: false                    # optional: see "Figure paths" below
figure_folders: [images, ../shared]    # optional: see "Figure paths" below
project_root: .                        # optional: see "Figure paths" below
# Multi-file keys (see docs/multi-file.md)
chapters: [chapters/intro.md, ...]    # optional: alternative to body embed syntax
companions: [si.md]                   # optional: companion documents (separate PDFs)
prefix: S                             # optional: counter prefix for companion docs
# Book-family template keys
dedication: "To my advisor"           # optional
list_of_figures: true                 # optional
list_of_tables: true                  # optional
bibliography_per_chapter: true        # optional: biblatex per-chapter refs
chapter-style: veelo                  # optional: memoir only
classicthesis-options: "parts"        # optional: classicthesis only
# Custom LaTeX preamble (see docs/preamble.md)
preamble: macros.tex                  # optional: file path or inline block scalar
```

Section-style metadata can also be given as markdown `# ...` headings. Any
of `# Abstract`, `# Acknowledgments`, `# Data Availability`, `# Appendix`,
`# Supplementary Material`, `# Significance`, `# Capsule`, `# Key Points`,
`# Plain Language Summary`, `# Author Contributions`, `# Competing Interests`,
`# Materials and Methods`, `# Funding`, `# Highlights`, `# Keywords` will be
extracted out of the body and injected into the right LaTeX command for the
target journal. Book-family templates additionally recognise `# Preface` and
`# Foreword`. The exact list each template recognises is in
[texmark/filters/__main__.py](/texmark/filters/__main__.py).

## Figure paths

texmark interprets `![](path)` URLs by the same rules as GitHub's markdown
renderer:

- **No leading slash** — relative to the markdown file's directory
  (the standard markdown spec).
- **Leading slash** — relative to the project root. By default the
  project root is detected via `git rev-parse --show-toplevel`, run from
  the markdown's directory so submodules and worktrees resolve to their
  own root rather than the outer repo's. For non-git projects, the
  invocation directory (CWD) is used. You can override either by passing
  `--project-root <path>` on the CLI (or `project_root: <path>` in the
  yaml front-matter).

Once resolved, each URL is rewritten in the generated `.tex` to be
relative to the build directory. The figure files stay where they are on
disk; nothing is copied.

If you would rather have short paths in the `.tex` (e.g. `eof.png`
instead of `../images/eof.png`), pass `--figure-folders <dir> [<dir> ...]`
on the CLI (yaml: `figure_folders: [<dir>, ...]`). Each folder is
interpreted relative to the current working directory and feeds LaTeX's
`\graphicspath`. Figures that live under any of these folders get short
URLs in the `.tex`; figures elsewhere keep the relative-to-build-dir form.
Folder search order is respected (first match wins, matching pdflatex's
own resolution).

For a self-contained build (e.g. to hand the `.tex` + figures to a
journal portal), pass `--copy-figures` on the CLI (yaml:
`copy_figures: true`). In that mode every referenced figure is copied
flat into `<build>/figures/`:

- Files keep their basename when unique.
- When two figures share a basename but have different contents, both are
  renamed to `<stem>-<short-content-hash><ext>` for disambiguation.
- Same file referenced from multiple paths collapses to a single bundled
  copy.
- A `.texmark-figures` manifest in `<build>/figures/` records which files
  texmark wrote, so the next build can delete only files it owns; files
  you put there by hand are preserved.

`--figure-folders` is ignored when `--copy-figures` is set (every figure
ends up in `<build>/figures/` either way).

Remote (`http(s)://`) figure URLs are always downloaded into
`<build>/figures/<hash>/<basename>` by the `texmark-download-images`
filter, regardless of these settings.

## Collect figures and tables at the end of the document

Just add
```yaml
collect_figures_and_tables: true
```
to your markdown yaml metadata.


## Advanced: latex template

The templates are written in [jinja2](https://jinja.palletsprojects.com).

Just copy from e.g. texmark/templates/science/template.tex to your own, e.g. custom_template.tex
And run again with:

    texmark example.md --pdf -j science -o build/example-science.pdf --tex build/example-science.tex --template custom_template.tex

The -j journal template option (here `science`) is still used to set custom filters (e.g. only `\cite` for Science, no `\citet` ; extract specific sections as metadata to be injected as `{{section}}` instead of `{{body}}` etc). The machinery is defined in [texmark/filters.py](/texmark/filters.py) and can in principle be extended or copied.
Two approaches are possible:
- just add more filters via the `--filters` command or in the yaml metadata.
- extend the existing filters in a module, e.g. custom_filter.py, that extends the `filters` dict from the `texmark.filters` module (see the source code to check the details). And then pass it via `--filters-module custom_filter` parameter (or `custom_filter` in the metadata) to prompt the texmark filter to load that module and make it available via `-j your-custom-name`. Note that will require you to explicitly pass `--template` as well. Unless you overwrite an existing filter.


## Ackowledgements

This project benefited greatly from AI support to extend the initial list of supported journals and further extend this package capability.
