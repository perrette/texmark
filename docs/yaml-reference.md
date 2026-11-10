# YAML reference

## Common yaml fields (all templates)

```yaml
title: "Paper title"
authors:
  - firstname: Mahé
    lastname: Perrette
    affiliation: 1              # integer index into `affiliations` (most templates)
    email: mahe.perrette@gmail.com
    corresponding: true         # optional: see Author roles below
    equalcontrib: true          # optional: see Author roles below
  - firstname: Co
    lastname: Author
    affiliation: 2
    equalcontrib: true
affiliations:
  - "Alfred Wegener Institute, ..."
  - "Another Institution"
date: "2026-05-26"
bibliography: references.bib
journal:
    template: <name>            # required: picks the journal template + filters
    draft: true                 # optional: true (default) = submission layout,
                                #   false = publication-ready typeset layout
    options: <str or list>      # optional: raw class options (overrides `draft`)
collect_figures_and_tables: true       # optional: see Figure paths page
figure-width: 80%                      # optional: pandoc figure default
figure-span: full                      # optional: wraps in figure* (full text width)
                                       #   per-figure override: ![cap](img){figure-span=full}
copy_figures: false                    # optional: see Figure paths page
figure_folders: [images, ../shared]    # optional: see Figure paths page
project_root: .                        # optional: see Figure paths page
# Multi-file keys (see Multi-file projects page)
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
# Custom LaTeX preamble (see Custom preamble page)
preamble: macros.tex                  # optional: file path or inline block scalar
# Build options (see Build backends page; the CLI flags override them)
engine: pdflatex                      # optional: pdflatex, xelatex, lualatex
backend: latexmk                      # optional: latexmk, raw, tectonic
rewrite_unicode: auto                 # optional: auto, on, off
draft: false                          # optional: figures as boxes (same as --draft)
progressive: false                    # optional: staged PDF builds (same as --progressive)
```

See the [Figure paths](figures.md), [Multi-file projects](multi-file.md), and
[Custom preamble](preamble.md) pages for the fields grouped above.

### Author roles

Two optional per-author keys:

- `corresponding: true` marks a corresponding author. Several authors may be
  marked. When no author has the key, the first author is the corresponding
  author. The journal templates that print a corresponding-author marker or
  email use the marked author(s): `copernicus`, `arxiv`, `ametsoc`,
  `elsarticle`, `springernature`, `science`, `pnas`. `agujournal` takes a
  single corresponding author and uses the first marked one. Templates that
  print every author's email (`book`, `report`, `memoir`, `classicthesis`)
  ignore the key.
- `equalcontrib: true` marks authors who contributed equally. It is rendered
  only by templates whose document class has a command for it, and ignored by
  all others:
    - `copernicus`: `\equalcontrib{i,j}` with the positions of the marked
      authors. copernicus.cls only renders it in Copernicus's production
      build, so it does not show in a local PDF.
    - `springernature`: `\equalcont{These authors contributed equally to this
      work.}` after each marked author (dagger symbol).
    - `pnas`: footnote marker 1 on the marked authors and
      `\equalauthors{These authors contributed equally to this work.}`; the
      corresponding-author marker then becomes 2. A top-level `equalauthors`
      field (or `# Equal Authors` section) takes priority, in which case the
      per-author key is ignored.
    - `science`: a dagger after the marked authors' names and the line
      "These authors contributed equally to this work." under the author list.

### journal.draft

Unified, template-independent layout switch for the article-class journal
templates. `true` (the default) produces the publisher's **submission**
layout — the 1.5-/double-spaced, usually single-column style wanted for peer
review. `false` switches to the **publication-ready** typeset layout (the
2-column journal look) as a preview of the printed article. Each template maps
the flag to the right class options for its document class; see the
[submission vs publication-ready table](journals/index.md#submission-vs-publication-ready-layout)
for what each journal does. `science` and `arxiv` have no production variant,
so the flag is a no-op there.

### draft

`draft: true` (or `--draft`) compiles the PDF with every figure replaced by a
box of the same size, which is faster and gives the same layout. It is
unrelated to `journal.draft`, which selects the submission or
publication-ready layout of the document class. See
[Draft builds](build-backends.md#draft-builds).

### progressive

`progressive: true` (or `--progressive`) publishes the PDF in stages: a draft
after one LaTeX pass, the draft with references resolved, then the full
build. See [Progressive builds](build-backends.md#progressive-builds).

### journal.options

Raw document-class options, given as a string (`twocol`) or a list
(`[final, 5p, times]`). When set, these are passed to `\documentclass` verbatim
and **override** `journal.draft`. Use this when you need a specific class
variant the `draft` flag does not cover; the per-journal docs pages under
[Journal templates](journals/index.md) list each class's full option set.

## Section-style metadata

Section-style metadata can also be given as markdown `# ...` headings. Any
of `# Abstract`, `# Acknowledgments`, `# Data Availability`, `# Appendix`,
`# Supplementary Material`, `# Significance`, `# Capsule`, `# Key Points`,
`# Plain Language Summary`, `# Author Contributions`, `# Competing Interests`,
`# Materials and Methods`, `# Funding`, `# Highlights`, `# Keywords` will be
extracted out of the body and injected into the right LaTeX command for the
target journal. Book-family templates additionally recognise `# Preface` and
`# Foreword`. The exact list each template recognises is in
[texmark/journals.py](https://github.com/perrette/texmark/blob/main/texmark/journals.py).
