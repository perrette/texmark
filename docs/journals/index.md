# Journal templates

Pick the template that matches your target journal and add it to the yaml
header of your markdown:

```yaml
journal:
    template: ametsoc          # template name, see table below
    draft: false               # optional — switch to the publication-ready layout
    # options: twocol          # optional, per-template raw class options — see the docs page
```

**Article-class templates** (single PDF, any journal):

| template | covers | example | docs |
| --- | --- | --- | --- |
| `copernicus` (aliases `cp`, `esd`, ...) | Copernicus / EGU: ACP, BG, CP, ESD, HESS, NHESS, TC, ... | [PDF](https://github.com/perrette/texmark/blob/main/build/example.pdf) | [docs](copernicus.md) |
| `science` | AAAS Science, Science Advances | [PDF](https://github.com/perrette/texmark/blob/main/build/example-science.pdf) | [docs](science.md) |
| `ametsoc` (aliases `jclim`, `jas`, `mwr`, `bams`, ...) | AMS: J. Climate, JAS, MWR, BAMS, ... | [PDF](https://github.com/perrette/texmark/blob/main/build/example-ametsoc.pdf) | [docs](ametsoc.md) |
| `arxiv` (alias `preprint`) | arXiv preprint, generic article-class | [PDF](https://github.com/perrette/texmark/blob/main/build/example-arxiv.pdf) | [docs](arxiv.md) |
| `elsarticle` (alias `elsevier`) | Elsevier: QSR, EPSL, GPC, Earth-Science Reviews, Cell, Lancet, ... | [PDF](https://github.com/perrette/texmark/blob/main/build/example-elsarticle.pdf) | [docs](elsarticle.md) |
| `agujournal` (aliases `agu`, `jgr`, `grl`, `james`, `wrr`, ...) | AGU: JGR family, GRL, Earth's Future, JAMES, ... | [PDF](https://github.com/perrette/texmark/blob/main/build/example-agujournal.pdf) | [docs](agujournal.md) |
| `springernature` (aliases `nature`, `naturecomms`, `natclimchange`, `natgeoscience`, `scirep`) | Springer Nature: Nature, Nature Communications, Nature Climate Change, Nature Geoscience, Scientific Reports, ... | [PDF](https://github.com/perrette/texmark/blob/main/build/example-springernature.pdf) | [docs](springernature.md) |
| `pnas` | PNAS | [PDF](https://github.com/perrette/texmark/blob/main/build/example-pnas.pdf) | [docs](pnas.md) |

**Book-family templates** (theses, monographs, multi-chapter documents):

| template | document class | structure | docs |
| --- | --- | --- | --- |
| `book` | `\documentclass{book}` | `\frontmatter` / `\mainmatter` / `\backmatter` | [docs](book.md) |
| `report` | `\documentclass{report}` | No front/main/back matter macros | [docs](report.md) |
| `memoir` | `\documentclass{memoir}` | `\frontmatter` / `\mainmatter` / `\backmatter`; configurable chapter styles | [docs](memoir.md) |
| `classicthesis` | `\documentclass{scrreprt}` + bundled `classicthesis.sty` | Bringhurst-inspired typography; no front/main/back matter macros | [docs](classicthesis.md) |

**Presentation templates** (Beamer slide decks):

| template | aliases | covers | docs |
| --- | --- | --- | --- |
| `beamer` | `slides`, `presentation` | Lecture slides, conference presentations, seminar talks | [docs](beamer.md) |

Book-family templates support `\include{...}` for chapters (enabling
`--only` for selective recompilation), front-matter YAML keys
(`dedication:`, `list_of_figures:`, etc.), and
`bibliography_per_chapter: true` for per-chapter biblatex bibliographies.

## Submission vs publication-ready layout

Every article-class template defaults to the publisher's **submission**
layout (the 1.5-/double-spaced, usually single-column style journals want for
peer review). Set `journal.draft: false` to switch that one template to its
**publication-ready** typeset layout (2-column journal look) for a preview of
how the article will appear in print:

| template | `draft: true` (default, submission) | `draft: false` (publication-ready) |
| --- | --- | --- |
| `copernicus` | `[short, manuscript]` one-column | `[short]` two-column production |
| `ametsoc` | no options — 1.5-spaced one-column | `twocol` two-column journal style |
| `elsarticle` | `preprint, 12pt` 1.5-spaced | `final, 5p, times` typeset 2-column |
| `agujournal` | `draft` double-spaced, line numbers | `final` single-spaced production |
| `springernature` | `…, referee` double-spaced one-column | `…, iicol` two-column production |
| `pnas` | always 2-column + DRAFT watermark | always 2-column, watermark removed |
| `science`, `arxiv` | single-column preprint (no production variant — flag is a no-op) | — |

`journal.draft` is the unified, template-independent switch. For finer control,
set [`journal.options`](../yaml-reference.md#journaloptions) to raw class
options — that overrides the flag and is passed to the document class verbatim.
The per-journal docs pages list each class's full option set.

!!! warning "Partial support only"
    Before submitting, you will likely need to hand-edit the final LaTeX —
    appendix structure, special sections (Methods Online, Extended Data,
    Significance, …) and journal-specific cross-reference macros are not all
    wired up automatically. Use the example PDF to confirm the layout looks
    reasonable, then run `texmark --tex out.tex` and finish the manuscript in
    LaTeX directly.

See the [YAML reference](../yaml-reference.md) for the common front-matter
fields shared by all templates.
