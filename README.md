# texmark

[![pypi](https://img.shields.io/pypi/v/texmark)](https://pypi.org/project/texmark)

Write scientific articles in markdown


## Installation

for development, after cloning:

    pip install -e .

and soon:

    pip install texmark

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

## Journal templates

Pick the template that matches your target journal and add it to the yaml
header of your markdown:

```yaml
journal:
    template: ametsoc          # template name, see table below
    options: twocol            # optional, per-template — see the docs page
```

| template | covers | citations | example | docs |
| --- | --- | --- | --- | --- |
| `copernicus` (aliases `cp`, `esd`, ...) | Copernicus / EGU: ACP, BG, CP, ESD, HESS, NHESS, TC, ... | natbib author-year | [PDF](build/example.pdf) | [docs](docs/journals/copernicus.md) |
| `science` | AAAS Science, Science Advances | `\cite{}` numbered | [PDF](build/example-science.pdf) | [docs](docs/journals/science.md) |
| `ametsoc` (aliases `jclim`, `jas`, `mwr`, `bams`, ...) | AMS: J. Climate, JAS, MWR, BAMS, ... | natbib (AMS) | [PDF](build/example-ametsoc.pdf) | [docs](docs/journals/ametsoc.md) |
| `arxiv` (alias `preprint`) | arXiv preprint, generic article-class | natbib `plainnat` | [PDF](build/example-arxiv.pdf) | [docs](docs/journals/arxiv.md) |
| `elsarticle` (alias `elsevier`) | Elsevier: QSR, EPSL, GPC, Earth-Science Reviews, Cell, Lancet, ... | natbib numbered | [PDF](build/example-elsarticle.pdf) | [docs](docs/journals/elsarticle.md) |
| `agujournal` (aliases `agu`, `jgr`, `grl`, `james`, `wrr`, ...) | AGU: JGR family, GRL, Earth's Future, JAMES, ... | apacite author-year | [PDF](build/example-agujournal.pdf) | [docs](docs/journals/agujournal.md) |
| `springernature` (aliases `nature`, `naturecomms`, `natclimchange`, `natgeoscience`, `scirep`) | Springer Nature: Nature, Nature Communications, Nature Climate Change, Nature Geoscience, Scientific Reports, ... | `\cite{}` numbered | [PDF](build/example-springernature.pdf) | [docs](docs/journals/springernature.md) |
| `pnas` | PNAS | `\cite{}` numbered | [PDF](build/example-pnas.pdf) | [docs](docs/journals/pnas.md) |

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
```

Section-style metadata can also be given as markdown `# ...` headings. Any
of `# Abstract`, `# Acknowledgments`, `# Data Availability`, `# Appendix`,
`# Supplementary Material`, `# Significance`, `# Capsule`, `# Key Points`,
`# Plain Language Summary`, `# Author Contributions`, `# Competing Interests`,
`# Materials and Methods`, `# Funding`, `# Highlights`, `# Keywords` will be
extracted out of the body and injected into the right LaTeX command for the
target journal. The exact list each template recognises is in
[texmark/filters/__main__.py](/texmark/filters/__main__.py).

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
