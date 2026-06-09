# YAML reference

## Common yaml fields (all templates)

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
```

See the [Figure paths](figures.md), [Multi-file projects](multi-file.md), and
[Custom preamble](preamble.md) pages for the fields grouped above.

## Section-style metadata

Section-style metadata can also be given as markdown `# ...` headings. Any
of `# Abstract`, `# Acknowledgments`, `# Data Availability`, `# Appendix`,
`# Supplementary Material`, `# Significance`, `# Capsule`, `# Key Points`,
`# Plain Language Summary`, `# Author Contributions`, `# Competing Interests`,
`# Materials and Methods`, `# Funding`, `# Highlights`, `# Keywords` will be
extracted out of the body and injected into the right LaTeX command for the
target journal. Book-family templates additionally recognise `# Preface` and
`# Foreword`. The exact list each template recognises is in
[texmark/filters/\_\_main\_\_.py](https://github.com/perrette/texmark/blob/main/texmark/filters/__main__.py).
