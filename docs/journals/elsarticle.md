# Elsevier — `elsarticle` class

**Template name:** `elsarticle`
**Alias:** `elsevier`
**Class file:** [elsarticle.cls](../../texmark/templates/elsarticle/elsarticle.cls) (CTAN, Jan 2026 build)
**Citation style:** natbib numbered (default `elsarticle-num.bst`)
**Example PDF:** [build/example-elsarticle.pdf](../../build/example-elsarticle.pdf)

## Covers

The `elsarticle` class is the single Elsevier LaTeX class used by **every**
Elsevier journal. A non-exhaustive list:

- Quaternary Science Reviews (QSR)
- Earth and Planetary Science Letters (EPSL)
- Global and Planetary Change (GPC)
- Earth-Science Reviews (ESR)
- Chemical Geology
- Palaeogeography, Palaeoclimatology, Palaeoecology
- Cell, Cell Reports, Current Biology, Neuron, …
- The Lancet (and its specialty journals)
- NeuroImage, Tetrahedron, Journal of Hydrology, Journal of Geophysical Research… (the AGU half), …

## YAML setup

```yaml
journal:
    template: elsarticle
    options: [final, 5p, times]              # default — full journal-typeset 2-col
    # options: [preprint, 12pt]              # double-blind submission style
    # options: [final, 3p, twocolumn, times] # alternative production layout
    # options: [review, preprint, 12pt]      # double-spaced for peer review
    name: "Quaternary Science Reviews"        # optional, sets \journal{...}
```

### Option groups

| group | meaning |
| --- | --- |
| `preprint` | 1.5-spaced preprint (Elsevier double-blind submission default) |
| `review` | Double-spaced review style — combine with `preprint` |
| `1p` | Single-column journal layout |
| `3p` | Double-column 3-part journal layout |
| `5p` | Double-column 5-part journal layout (looks closest to a typeset article) |
| `twocolumn` | Two-column variant — combine with `1p` / `3p` / `5p` |
| `final` | Final-production style (vs. `preprint`) |
| `authoryear` | Switch to author-year citations (pair with `elsarticle-harv.bst`) |
| `times` | Use Times font |

## Recognised section headings

- `# Abstract`
- `# Highlights` — rendered into `\begin{highlights}` itemize
- `# Keywords` — rendered into `\begin{keyword}` with `\sep` separators
- `# Acknowledgements`
- `# Data Availability`
- `# CRediT` / `# Author Contributions` — rendered as
  `\section*{CRediT authorship contribution statement}`
- `# Competing Interests` — rendered as
  `\section*{Declaration of competing interest}`
- `# Appendix`

## Gotchas

- `elsarticle` does **not** load `amsmath` or `hyperref` from its class. The
  template loads both, so `\begin{align}` and `\href{}` work out of the
  box.
- The default `elsarticle-num.bst` produces numbered references. If you
  need author-year, use `options: [authoryear, ...]` and set
  `biblio_style: elsarticle-harv` (or the named variant).
